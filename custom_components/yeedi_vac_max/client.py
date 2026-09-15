"""Small asynchronous Yeedi-DE HTTPS client.

Protocol facts and public app identifiers: see docs/PROTOCOL.md.
This original implementation uses no code or runtime from a third-party fork.
"""
from __future__ import annotations

import asyncio
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

# Public Yeedi application signing identifiers, NOT user credentials.
# Provenance: ecovacs-deebot.js constants.js, pinned in docs/PROTOCOL.md.
LOGIN_KEY = "1581917520081"
LOGIN_SECRET = "ed5b3dd9a0253de7d90305d077eb5fee"
AUTH_KEY = "1581923437995"
AUTH_SECRET = "304a71592690995b2bb304e66b5ddee6"
PORTAL = "https://portal-eu.ecouser.net/api/"
FAN_SPEEDS = {"Quiet": 1000, "Normal": 0, "Max": 1}
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
    if response.get("ret") != "ok":
        raise CloudError(f"Portal rejected command (code {error})")
    payload = response.get("resp")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            raise CloudError("Invalid device response") from None
    body = object_value(object_value(payload).get("body"))
    code = body.get("code")
    if code is not None and str(code) != "0":
        raise CommandRejected(f"Device rejected command (code {numeric_code(code)})")
    if writing and code is None:
        raise CloudError("Device acknowledgement missing")
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

    async def _request(self, method: str, url: str, *, retry: bool = False, **kwargs) -> dict:
        """Bound requests; no retries for writes or login, no raw exception logging."""
        for attempt in range(2 if retry else 1):
            try:
                async with self._requests:
                    async with self.session.request(
                        method, url, timeout=aiohttp.ClientTimeout(total=15),
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
                        return object_value(result)
            except RateLimited:
                raise
            except (aiohttp.ClientError, TimeoutError, CannotConnect):
                if attempt == 0 and retry:
                    await asyncio.sleep(1)
                    continue
                raise CannotConnect("Cannot reach Yeedi cloud") from None
            except (ValueError, TypeError):
                raise CloudError("Invalid JSON from cloud") from None
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

    async def command(self, robot: Robot, name: str, data: dict | None = None,
                      *, writing: bool = False) -> dict:
        await self.authenticate()
        response = await self._request(
            "POST", PORTAL + "iot/devmanager.do", retry=not writing,
            params={"cv": "1.94.76", "t": "a", "av": "1.3.0", "mid": TARGET_CLASS_ID,
                    "did": robot.did, "td": "q", "u": self.user_id},
            json={"cmdName": name, "payloadType": "j", "auth": self._auth(), "td": "q",
                  "toId": robot.did, "toRes": robot.resource, "toType": TARGET_CLASS_ID,
                  "payload": {"header": {"pri": "1", "ts": int(time.time()*1000),
                                         "tzm": 480, "ver": "0.0.50"},
                              "body": {"data": data or {}}}})
        return command_body(response, writing=writing)

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
