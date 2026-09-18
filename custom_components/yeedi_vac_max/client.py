"""Small asynchronous Yeedi-DE HTTPS client.

Protocol facts and public app identifiers: see docs/PROTOCOL.md.
This original implementation uses no code or runtime from a third-party fork.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import logging
import math
import time
from typing import Any
from uuid import uuid4

import aiohttp

from .const import TARGET_CLASS_ID
from .structure_diagnostics import COMMANDS, LEGACY_COMMANDS, response_structure
from .geometry_diagnostics import value_format, aggregate_formats
from .transport_diagnostics import empty_probe, major_shape, minor_shape, piece_indices
from .map_data import (YeediMap, YeediRoom, RobotPosition, DockPosition,
                       identifier, position, polygon, fallback_name)

# Public Yeedi application signing identifiers, NOT user credentials.
# Provenance: ecovacs-deebot.js constants.js, pinned in docs/PROTOCOL.md.
LOGIN_KEY = "1581917520081"
LOGIN_SECRET = "ed5b3dd9a0253de7d90305d077eb5fee"
AUTH_KEY = "1581923437995"
AUTH_SECRET = "304a71592690995b2bb304e66b5ddee6"
PORTAL = "https://portal-eu.ecouser.net/api/"
FAN_SPEEDS = {"Quiet": 1000, "Normal": 0, "Max": 1}
HTTP_TIMEOUT = 15
READ_ATTEMPTS = 2
READ_RETRY_DELAY = 1
READ_RETRY_BUDGET = HTTP_TIMEOUT * READ_ATTEMPTS + READ_RETRY_DELAY * (READ_ATTEMPTS - 1)
LEGACY_PROBE_TIMEOUT = HTTP_TIMEOUT + 3
MAP_REQUEST_TIMEOUT = READ_RETRY_BUDGET + 9
MAP_DISCOVERY_TIMEOUT = MAP_REQUEST_TIMEOUT + 2 * LEGACY_PROBE_TIMEOUT + 1
TRANSPORT_PROBE_TIMEOUT = 60
_LOGGER = logging.getLogger(__name__)


class CloudError(Exception):
    """Sanitized error safe for HA logs."""


class InvalidAuth(CloudError):
    """Credentials rejected."""


class VerificationRequired(CloudError):
    """Cloud requires an additional verification flow."""


class CannotConnect(CloudError):
    """Transport failed."""


class DeviceOffline(CloudError):
    """Device did not answer."""


class RateLimited(CannotConnect):
    """Wait for the next poll; never immediately repeat a throttled request."""


class CommandRejected(CloudError):
    """Device rejected a command."""


class CommandUncertain(CloudError):
    """No reliable acknowledgement; do not repeat the write."""


class CommandTimeout(CommandUncertain, CannotConnect):
    """Request timed out with unknown device-side outcome."""


def md5(value: str) -> str:
    """MD5 is mandated by the cloud protocol, not used for local password storage."""
    return hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()


def signed(params: dict, metadata: dict, key: str, secret: str) -> dict:
    """Produce a fresh parameter mapping with the protocol signature."""
    fields = metadata | params
    text = key + "".join(f"{name}={fields[name]}" for name in sorted(fields)) + secret
    return params | {"authAppkey": key, "authSign": md5(text)}


def numeric_code(value: Any) -> str:
    """Never echo arbitrary cloud strings that might contain account data."""
    text = str(value)
    return text if text.isdecimal() and len(text) <= 8 else "unknown"


def object_value(value: Any) -> dict:
    if not isinstance(value, dict):
        raise CloudError("Unexpected cloud response structure")
    return value


def command_body(response: dict, *, writing: bool = False) -> dict:
    """Validate both portal and device acknowledgements; never assume success."""
    error = numeric_code(response.get("errno"))
    if error in {"4200", "500"}:
        raise DeviceOffline("Device offline or response timed out")
    if response.get("ret") == "fail":
        raise CommandRejected(f"Portal rejected command (code {error})")
    if response.get("ret") != "ok":
        raise CommandUncertain("Portal acknowledgement missing")
    payload = response.get("resp")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            raise CommandUncertain("Invalid device response") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("body"), dict):
        raise CommandUncertain("Device response structure missing")
    body = payload["body"]
    code = body.get("code")
    if code is not None and str(code) != "0":
        raise CommandRejected(f"Device rejected command (code {numeric_code(code)})")
    if writing and code is None:
        raise CommandUncertain("Device acknowledgement missing")
    return body


def activity(clean: dict, charge: dict) -> str | None:
    """Only return states evidenced by the current response."""
    if clean.get("trigger") == "alert":
        return "error"
    state = clean.get("state")
    motion = object_value(clean.get("cleanState", {})).get("motionState")
    if state == "goCharging" or motion == "goCharging":
        return "returning"
    if state in {"clean", "washing"}:
        if motion == "working":
            return "cleaning"
        if motion == "pause":
            return "paused"
    if charge.get("isCharging") in (1, "1"):
        return "docked"
    if state == "idle":
        return "idle"
    return None


@dataclass(frozen=True)
class Robot:
    did: str
    resource: str
    name: str


class YeediClient:
    """Use the HA-owned session; retain tokens only in memory."""

    def __init__(self, session: aiohttp.ClientSession, account: str, password: str,
                 country: str, device_id: str):
        if country.upper() != "DE":
            raise ValueError("Only DE has been implemented")
        self.session = session
        self.account = account
        self.password = password
        self.device_id = device_id
        self.user_id = ""
        self.token = ""
        self.expires = 0.0
        self._auth_lock = asyncio.Lock()
        self._requests = asyncio.Semaphore(3)
        self._structure = {}
        self._geometry = {}
        self._transport = {}

    async def _request(self, method: str, url: str, *, retry: bool = False, **kwargs) -> dict:
        """Bound requests; no retries for writes or login, no raw exception logging."""
        for attempt in range(READ_ATTEMPTS if retry else 1):
            try:
                async with self._requests:
                    async with self.session.request(
                        method, url, timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
                        allow_redirects=False, **kwargs
                    ) as response:
                        if response.status in (401, 403):
                            self.expires = 0
                            raise InvalidAuth("Cloud authentication rejected")
                        if response.status == 429:
                            raise RateLimited("Cloud rate limit; wait before retrying")
                        if response.status >= 500:
                            raise CannotConnect("Cloud temporarily unavailable")
                        if response.status != 200:
                            raise CloudError("Unexpected HTTP response")
                        result = await response.json(content_type=None)
                        if not isinstance(result, dict):
                            raise CommandUncertain("Invalid cloud response structure")
                        return object_value(result)
            except RateLimited:
                raise
            except TimeoutError:
                if attempt == 0 and retry:
                    await asyncio.sleep(READ_RETRY_DELAY)
                    continue
                raise CommandTimeout("Cloud request timed out; outcome unknown") from None
            except (aiohttp.ClientError, CannotConnect):
                if attempt == 0 and retry:
                    await asyncio.sleep(READ_RETRY_DELAY)
                    continue
                raise CannotConnect("Cannot reach Yeedi cloud") from None
            except (ValueError, TypeError):
                raise CommandUncertain("Invalid JSON from cloud") from None
        raise CannotConnect("Cannot reach Yeedi cloud")

    @staticmethod
    def _auth_data(response: dict) -> dict:
        code = str(response.get("code"))
        if code in {"1005", "1010"}:
            raise InvalidAuth("Yeedi account or password rejected")
        if code == "1013":
            raise VerificationRequired("Yeedi requires device verification")
        if code != "0000":
            raise CloudError(f"Yeedi login failed (code {numeric_code(code)})")
        return object_value(response.get("data"))

    async def authenticate(self) -> None:
        async with self._auth_lock:
            if self.token and time.monotonic() < self.expires:
                return
            meta = dict(country="de", lang="EN", deviceId=self.device_id,
                        appCode="yd_global_e", appVersion="1.3.0",
                        channel="google_play", deviceType="1")
            path = "/".join(meta[k] for k in (
                "country", "lang", "deviceId", "appCode", "appVersion", "channel", "deviceType"))
            params = dict(account=self.account, password=md5(self.password),
                          requestId=uuid4().hex, authTimespan=int(time.time() * 1000),
                          authTimeZone="GMT-8")
            login = self._auth_data(await self._request(
                "GET", f"https://gl-de-api.yeedi.com/v1/private/{path}/user/login",
                params=signed(params, meta, LOGIN_KEY, LOGIN_SECRET)))
            try:
                uid, access = login["uid"], login["accessToken"]
                params = dict(uid=uid, accessToken=access, bizType="", openId="global",
                              deviceId=self.device_id, authTimespan=int(time.time() * 1000))
                code = self._auth_data(await self._request(
                    "GET", "https://gl-de-openapi.yeedi.com/v1/global/auth/getAuthCode",
                    params=signed(params, {"openId": "global"}, AUTH_KEY, AUTH_SECRET)))
                result = await self._request("POST", PORTAL + "users/user.do", json={
                    "todo": "loginByItToken", "edition": "ECOGLOBLE",
                    "userId": uid, "token": code["authCode"], "realm": "ecouser.net",
                    "resource": self.device_id, "org": "ECOYDWW", "last": "", "country": "DE"})
                if result.get("result") != "ok":
                    raise CloudError("Yeedi token exchange rejected")
                token, user = result["token"], result["userId"]
                lifetime = float(result.get("last", 604800000)) / 1000
                if not isinstance(token, str) or not token or not isinstance(user, str) or not user:
                    raise ValueError
                if not math.isfinite(lifetime) or lifetime <= 0:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                raise CloudError("Incomplete Yeedi authentication response") from None
            self.token, self.user_id = token, user
            # Both reference clients renew by login; no separate refresh-token grant is verified.
            self.expires = time.monotonic() + min(lifetime * 0.99, 604800)

    def _auth(self) -> dict:
        return {
            "with": "users", "userid": self.user_id, "realm": "ecouser.net",
            "token": self.token, "resource": self.device_id}

    async def devices(self) -> list[Robot]:
        await self.authenticate()
        devices = {}
        for path, command in (("users/user.do", "GetDeviceList"),
                              ("appsvr/app.do", "GetGlobalDeviceList")):
            response = await self._request("POST", PORTAL + path, retry=True, json={
                "userid": self.user_id, "todo": command, "auth": self._auth()})
            if not isinstance(response.get("devices"), list):
                raise CloudError("Device list missing from Yeedi response")
            for item in response["devices"]:
                item = object_value(item)
                if item.get("class") != TARGET_CLASS_ID:
                    continue
                did, resource = item.get("did"), item.get("resource")
                if not isinstance(did, str) or not did or not isinstance(resource, str) or not resource:
                    raise CloudError("Vac Max device identifiers missing")
                devices[did] = Robot(did, resource, str(item.get("nick") or "Yeedi Vac Max"))
        return list(devices.values())

    async def command(self, robot: Robot, name: str, data: dict | list | None = None,
                      *, writing: bool = False) -> dict:
        """Capture only safe structure of the four optional read commands."""
        probe = None
        if not writing and name in COMMANDS:
            probe = {"attempted": True, "command_success": False,
                     "response_received": False, "outcome": "pending"}
            self._structure.setdefault(robot.did, {})[name] = probe
        try:
            result = await self._command(robot, name, data, writing=writing, probe=probe)
        except asyncio.CancelledError:
            if probe is not None:
                probe["outcome"] = "cancelled_or_budget_expired"
            raise
        except CloudError as err:
            if probe is not None:
                probe["outcome"] = next((label for cls, label in (
                    (DeviceOffline, "offline"), (CommandRejected, "rejected"),
                    (RateLimited, "busy"), (CommandTimeout, "timeout"),
                    (InvalidAuth, "authentication"), (VerificationRequired, "authentication"),
                    (CommandUncertain, "unclear"), (CannotConnect, "transport"))
                    if isinstance(err, cls)), "cloud_error")
            raise
        if probe is not None:
            probe.update(command_success=True, outcome="accepted_read")
        return result

    def structure_diagnostics(self, robot: Robot) -> dict:
        """No IDs in output; a copy prevents diagnostic consumers modifying state."""
        recorded = self._structure.get(robot.did, {})
        return {name: deepcopy(recorded.get(name, {"attempted": False})) for name in COMMANDS}

    def geometry_diagnostics(self, robot: Robot) -> dict:
        """Latest room-read cycle only, aggregate format flags without raw data."""
        return deepcopy(self._geometry.get(robot.did, aggregate_formats([])))

    def transport_diagnostics(self, robot: Robot) -> dict:
        return deepcopy(self._transport.get(robot.did, empty_probe()))

    async def _command(self, robot: Robot, name: str, data=None, *, writing=False, probe=None):
        if name in (*LEGACY_COMMANDS, "getMapInfo", "getMinorMap") and writing:
            raise ValueError("Legacy map probes are read-only")
        try:
            await self.authenticate()
        except (CommandUncertain, CannotConnect):
            # No device write has been attempted; status cannot confirm a login.
            raise CannotConnect("Authentication transport failed before command") from None
        response = await self._device_request(writing,
            "POST", PORTAL + "iot/devmanager.do", retry=not writing and name not in LEGACY_COMMANDS,
            params={"cv": "1.94.76", "t": "a", "av": "1.3.0", "mid": TARGET_CLASS_ID,
                    "did": robot.did, "td": "q", "u": self.user_id},
            json={"cmdName": name, "payloadType": "j", "auth": self._auth(), "td": "q",
                  "toId": robot.did, "toRes": robot.resource, "toType": TARGET_CLASS_ID,
                  "payload": {"header": {"pri": "1", "ts": int(time.time()*1000),
                                         "tzm": 480, "ver": "0.0.50"},
                              "body": {"data": data or {}}}})
        if probe is not None:
            probe.update(response_structure(response, outline=name == "getMapInfo"))
        return command_body(response, writing=writing)

    async def _device_request(self, writing, *args, **kwargs):
        try:
            return await self._request(*args, **kwargs)
        except (RateLimited, CommandTimeout):
            raise
        except CannotConnect:
            if writing:
                raise CommandUncertain("Device request transport outcome unknown") from None
            raise

    async def maps(self, robot: Robot) -> tuple[YeediMap, ...]:
        try:
            async with asyncio.timeout(MAP_REQUEST_TIMEOUT):
                body = await self.command(robot, "getCachedMapInfo")
        except CommandTimeout:
            candidate = await self.probe_legacy_maps(robot)
            if candidate is None:
                raise CloudError("Legacy discovery returned no valid current map") from None
            return (candidate,)
        info = object_value(body.get("data")).get("info")
        if not isinstance(info, list) or len(info) > 100:
            raise CloudError("Invalid map metadata")
        result = {}
        for item in info:
            if not isinstance(item, dict):
                continue
            mid = identifier(item.get("mid"))
            if mid is None or mid == "0":
                continue
            if mid in result:
                raise CloudError("Ambiguous map metadata")
            name = item.get("name")
            result[mid] = YeediMap(mid, name if isinstance(name, str) else None,
                                   item.get("using") in (1, "1"))
        return tuple(result.values())

    async def probe_legacy_maps(self, robot: Robot) -> YeediMap | None:
        """Read legacy structure and return only the evidenced current map ID.

        Never interpret state or access MajorMap.value. A failed probe yields no map.
        """
        recorded = self._structure.setdefault(robot.did, {})
        for name in LEGACY_COMMANDS:
            recorded.pop(name, None)  # Do not show an old result as this cycle's probe.
        for name in LEGACY_COMMANDS:
            try:
                async with asyncio.timeout(LEGACY_PROBE_TIMEOUT):
                    body = await self.command(robot, name)
                if name == "getMajorMap":
                    raw_mid = object_value(body.get("data")).get("mid")
                    mid = identifier(raw_mid) if isinstance(raw_mid, str) else None
                    if mid is not None and mid != "0":
                        return YeediMap(mid, None, True)
            except (InvalidAuth, VerificationRequired, DeviceOffline, RateLimited):
                break
            except (CloudError, TimeoutError):
                continue
        return None

    async def probe_map_info(self, robot: Robot, map_id: str) -> None:
        """One bounded outline read; discard result, keep safe structure only."""
        if not isinstance(map_id, str) or identifier(map_id) != map_id or map_id == "0":
            return
        try:
            async with asyncio.timeout(MAP_REQUEST_TIMEOUT):
                await self.command(robot, "getMapInfo", {"mid": map_id, "type": "ol"})
        except (CloudError, TimeoutError):
            pass  # Optional diagnostics must not invalidate discovered rooms.
        await self.probe_map_transport(robot, map_id)

    async def probe_map_transport(self, robot: Robot, map_id: str) -> None:
        """Optional direct comparison, separate from functional map discovery."""
        result = empty_probe()
        self._transport[robot.did] = result
        if not isinstance(map_id, str) or identifier(map_id) != map_id or map_id == "0":
            return
        budget = asyncio.timeout(TRANSPORT_PROBE_TIMEOUT)
        try:
            async with budget:
                async with asyncio.timeout(LEGACY_PROBE_TIMEOUT):
                    body = await self.command(robot, "getMajorMap")
                data = body.get("data")
                result['direct_major_map_probe'] = major_shape(data)
                if not isinstance(data,dict) or data.get('mid') != map_id:
                    return
                result['map_transport_probe']['direct_major_map']['usable_structure'] = True
                indices = piece_indices(data.get('value'))
                # No raw data or CRC tokens retained across any further await.
                del data, body
                if indices is None:
                    return
                result['map_transport_probe']['direct_major_map']['piece_list_detected'] = True
                minor = result['direct_minor_map_probe']
                for index in indices:
                    minor['attempted_count'] += 1
                    result['map_transport_probe']['direct_minor_map']['attempted'] = True
                    try:
                        async with asyncio.timeout(MAP_REQUEST_TIMEOUT):
                            response = await self.command(robot, "getMinorMap", {
                                'mid':map_id, 'pieceIndex':index, 'type':'ol'})
                        minor['accepted_count'] += 1
                        payload = response.get('data')
                        shape = minor_shape(payload)
                        group = next((g for g in minor['formats'] if g['format'] == shape), None)
                        if group is None:
                            minor['formats'].append({'count':1,'format':shape})
                        else:
                            group['count'] += 1
                        if isinstance(payload,dict) and payload.get('mid',map_id) == map_id:
                            if any(isinstance(payload.get(k),str) and payload[k] for k in ('value','pieceValue')):
                                result['map_transport_probe']['direct_minor_map']['nonempty_payload_seen'] = True
                        del payload, response
                    except (CommandTimeout, TimeoutError):
                        minor['timeout_count'] += 1
                    except CommandRejected:
                        minor['rejected_count'] += 1
                    except (InvalidAuth, VerificationRequired, DeviceOffline, RateLimited):
                        break
                    except CloudError:
                        pass
                    except asyncio.CancelledError:
                        # Includes expiration of the aggregate diagnostic budget.
                        if budget.expired():
                            minor['timeout_count'] += 1
                        raise
                    finally:
                        probe = self._structure.get(robot.did, {}).get('getMinorMap', {})
                        minor['response_count'] += int(probe.get('response_received',False))
        except (CloudError, TimeoutError, ValueError, TypeError, RecursionError):
            pass  # Optional analysis never changes availability, rooms or services.

    async def rooms(self, robot: Robot, map_id: str) -> tuple[YeediRoom, ...]:
        formats = []
        polygon_count = 0
        self._geometry[robot.did] = aggregate_formats(formats)
        body = await self.command(robot, "getMapSet", {"mid": map_id, "type": "ar"})
        data = object_value(body.get("data"))
        if "mid" in data and identifier(data["mid"]) != map_id:
            raise CloudError("Map response mismatch")
        subsets = data.get("subsets")
        if not isinstance(subsets, list) or len(subsets) > 100:
            raise CloudError("Invalid room list")
        msid = identifier(data.get("msid"))
        rooms = {}
        for item in subsets:
            if not isinstance(item, dict):
                continue
            rid = identifier(item.get("mssid"))
            if rid is None or rid in rooms:
                continue
            detail = item
            observed_format = None
            if "value" not in item or not item.get("name"):
                try:
                    request = {"mid": map_id, "type": "ar", "mssid": rid}
                    if msid is not None:
                        request["msid"] = msid
                    response = await self.command(robot, "getMapSubSet", request)
                    candidate = object_value(response.get("data"))
                    if (identifier(candidate.get("mssid")) == rid
                            and identifier(candidate.get("mid", map_id)) == map_id):
                        detail = item | candidate
                        observed_format = value_format(candidate.get("value"), present="value" in candidate)
                except (CloudError, TimeoutError):
                    pass
            name = detail.get("name")
            rooms[rid] = YeediRoom(
                rid, name.strip() if isinstance(name, str) and name.strip() else fallback_name(len(rooms)),
                  identifier(detail.get("subtype")), polygon(detail.get("value"), detail.get("compress")))
            if observed_format is not None:
                formats.append(observed_format)
                polygon_count += int(rooms[rid].polygon is not None)
                self._geometry[robot.did] = aggregate_formats(formats, polygon_count)
        return tuple(rooms.values())

    async def positions(self, robot: Robot) -> tuple[RobotPosition | None, DockPosition | None]:
        body = await self.command(robot, "getPos", ["chargePos", "deebotPos"])
        data = object_value(body.get("data"))
        dock = data.get("chargePos")
        dock = dock[0] if isinstance(dock, list) and len(dock) == 1 else None
        return position(data.get("deebotPos"), RobotPosition), position(dock, DockPosition)

    async def snapshot(self, robot: Robot) -> dict:
        results = {}
        for name in ("getBattery", "getCleanInfo", "getChargeState", "getSpeed"):
            try:
                body = await self.command(robot, name)
                results[name] = object_value(body.get("data"))
            except (InvalidAuth, VerificationRequired):
                raise
            except DeviceOffline:
                if name == "getBattery":
                    return {"online": False, "activity": None, "battery": None, "fan_speed": None}
                results[name] = {}
            except CloudError as err:
                if name == "getBattery":
                    raise
                _LOGGER.debug("%s could not be read: %s", name, err)
                results[name] = {}
        raw_battery = results["getBattery"].get("value")
        try:
            battery = int(raw_battery)
            if not 0 <= battery <= 100:
                raise ValueError
        except (TypeError, ValueError):
            raise CloudError("Invalid battery response") from None
        speed = results["getSpeed"].get("speed")
        fan = next((k for k, v in FAN_SPEEDS.items() if str(v) == str(speed)), None)
        return {"online": True, "battery": battery, "fan_speed": fan,
                "activity": activity(results["getCleanInfo"], results["getChargeState"])}

    def close(self) -> None:
        """Clear memory only; the shared aiohttp session belongs to HA."""
        self.token = self.password = ""
        self.expires = 0
        self._structure.clear()
        self._geometry.clear()
        self._transport.clear()
