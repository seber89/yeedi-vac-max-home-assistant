"""Central base/spatial state and serialized, never-retried device writes."""
import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
import time

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (CloudError, InvalidAuth, VerificationRequired, CommandUncertain,
                     DeviceOffline, RateLimited, CommandRejected, READ_RETRY_BUDGET,
                     MAP_REQUEST_TIMEOUT, MAP_DISCOVERY_TIMEOUT)
from .map_data import YeediMap, YeediRoom, RobotPosition, DockPosition, identifier

_LOGGER = logging.getLogger(__name__)
MAP_INTERVAL = 3600
MAP_READ_TIMEOUT = MAP_REQUEST_TIMEOUT  # Primary read stays 40s; discovery adds bounded legacy reads.
MAP_ERROR_BACKOFF = 180
ROOM_REFRESH_TIMEOUT = READ_RETRY_BUDGET + 9  # 40s total for MapSet plus optional details.
COMMAND_GAP = 1.5
MAX_PENDING = 4


@dataclass(repr=False)
class SpatialState:
    maps: tuple[YeediMap, ...] = ()
    active_map: YeediMap | None = None
    rooms: tuple[YeediRoom, ...] = ()
    robot_position: RobotPosition | None = None
    dock_position: DockPosition | None = None
    metadata_valid: bool = False
    rooms_valid: bool = False
    next_map_refresh: float = 0

    @property
    def room_generation(self):
        """Local structural identity only; never included in diagnostics."""
        return tuple(sorted({room.room_id for room in self.rooms}))


@dataclass
class CommandState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pending: int = 0
    last_end: float = 0
    last_key: tuple | None = None
    last_confirmation: str | None = None


class YeediCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client, robots):
        super().__init__(hass, _LOGGER, name="Yeedi Vac Max",
                         config_entry=entry, update_interval=timedelta(seconds=60))
        self.client = client
        self.robots = robots
        self.spatial = {r.did: SpatialState() for r in robots}
        self.commands = {r.did: CommandState() for r in robots}
        self._observed = {}

    @property
    def rooms(self):
        """Read-only view of valid cached rooms, keyed by robot ID."""
        return {did: tuple(room for room in state.rooms
                           if identifier(room.room_id) == room.room_id
                           and "," not in room.room_id)
                if state.metadata_valid and state.rooms_valid and state.active_map
                and time.monotonic() < state.next_map_refresh else ()
                for did, state in self.spatial.items()}

    def _remember(self, robot, snapshot):
        self._observed[robot.did] = (time.monotonic(), dict(snapshot))

    def _already_done(self, robot, command, data):
        observed = self._observed.get(robot.did)
        if not observed or time.monotonic() - observed[0] > 65:
            return False
        snapshot = observed[1]
        if not self.last_update_success or not snapshot.get("online"):
            return False
        current = snapshot.get("activity")
        if command == "charge" and data.get("act") == "go":
            return current in {"docked", "returning"}
        if command != "clean" or data.get("type") not in (None, "auto"):
            return False  # A new room selection must never be skipped as auto-clean.
        return current in {"start": {"cleaning"}, "resume": {"cleaning"},
                           "pause": {"paused"}, "stop": {"idle", "docked"}}.get(data.get("act"), set())

    async def _validate_room_command(self, robot, data, expected_map_id, expected_generation):
        """Validate cached IDs and recheck map identity under the existing lock."""
        state = self.spatial[robot.did]
        selected = data.get("content")
        ids = selected.split(",") if isinstance(selected, str) else []
        if (not expected_map_id or not state.active_map
                or state.active_map.map_id != expected_map_id or not ids
                or state.room_generation != expected_generation
                or not set(ids) <= {room.room_id for room in self.rooms[robot.did]}):
            raise HomeAssistantError("Room selection unavailable or stale; refresh room mapping")
        map_verified = False
        try:
            async with asyncio.timeout(MAP_DISCOVERY_TIMEOUT):
                maps = await self.client.maps(robot)
            active = [item for item in maps if item.active]
            if len(active) != 1 or active[0].map_id != expected_map_id:
                state.rooms = ()
                state.rooms_valid = state.metadata_valid = False
                state.next_map_refresh = 0
                await self._spatial_refresh(robot, force=True)
                self.async_update_listeners()
                raise HomeAssistantError("Active map changed; select rooms again")
            map_verified = True
            # A map can keep its ID while its room partition changes. Check it
            # under the same write lock, rather than trusting the hourly cache.
            async with asyncio.timeout(ROOM_REFRESH_TIMEOUT):
                rooms = await self.client.rooms(robot, expected_map_id)
            state.rooms = rooms
            state.rooms_valid = True
            state.next_map_refresh = time.monotonic() + MAP_INTERVAL
            self.async_update_listeners()
            if (state.room_generation != expected_generation
                    or not set(ids) <= {room.room_id for room in self.rooms[robot.did]}):
                raise HomeAssistantError("Room mapping changed; configure area mapping again")
        except (CloudError, TimeoutError):
            state.rooms_valid = False
            state.rooms = ()
            if not map_verified:
                state.metadata_valid = False
            state.next_map_refresh = time.monotonic() + MAP_ERROR_BACKOFF
            self.async_update_listeners()
            raise HomeAssistantError("Could not verify active map; no room command sent") from None

    async def _spatial_refresh(self, robot, *, force=False):
        state = self.spatial[robot.did]
        try:
            async with asyncio.timeout(8):
                state.robot_position, state.dock_position = await self.client.positions(robot)
        except (CloudError, TimeoutError):
            state.robot_position = state.dock_position = None
        if not force and time.monotonic() < state.next_map_refresh:
            return
        state.metadata_valid = False
        state.rooms_valid = False
        self.async_update_listeners()
        try:
            async with asyncio.timeout(MAP_DISCOVERY_TIMEOUT):
                maps = await self.client.maps(robot)
            active = [m for m in maps if m.active]
            selected = active[0] if len(active) == 1 else None
            if selected != state.active_map:
                state.rooms = ()
            state.maps, state.active_map = maps, selected
            state.metadata_valid = True
            self.async_update_listeners()
            if selected is None:
                state.rooms = ()
                state.next_map_refresh = time.monotonic() + MAP_INTERVAL
                return
            async with asyncio.timeout(ROOM_REFRESH_TIMEOUT):
                state.rooms = await self.client.rooms(robot, selected.map_id)
                state.rooms_valid = True
            state.next_map_refresh = time.monotonic() + MAP_INTERVAL
        except (CloudError, TimeoutError):
            state.rooms_valid = False
            state.rooms = ()
            state.next_map_refresh = time.monotonic() + MAP_ERROR_BACKOFF
            # Retain cache but mark stale; future room commands must require validity.
        if state.metadata_valid and state.active_map is not None:
            # Optional read-only probe after the normal room flow, never during
            # room-command preflight and never on each minute's cached poll.
            await self.client.probe_map_info(robot, state.active_map.map_id)

    async def async_refresh_map_data(self, robot):
        """Explicit refresh hook; reload creates fresh caches automatically."""
        async with self.commands[robot.did].lock:
            await self._spatial_refresh(robot, force=True)
        self.async_update_listeners()

    async def _poll_robot(self, robot):
        async with self.commands[robot.did].lock:
            async with asyncio.timeout(60):
                base = await self.client.snapshot(robot)
            self._remember(robot, base)
            if base.get("online"):
                await self._spatial_refresh(robot)
            else:
                self.spatial[robot.did].robot_position = None
                self.spatial[robot.did].dock_position = None
                self.spatial[robot.did].metadata_valid = False
                self.spatial[robot.did].rooms_valid = False
            return base

    async def _async_update_data(self):
        try:
            states = await asyncio.gather(*(self._poll_robot(r) for r in self.robots))
            return {r.did: state for r, state in zip(self.robots, states, strict=True)}
        except (InvalidAuth, VerificationRequired):
            raise ConfigEntryAuthFailed("Yeedi authentication requires attention") from None
        except (CloudError, TimeoutError):
            raise UpdateFailed("Could not refresh Yeedi devices") from None

    @staticmethod
    def _expected(command, data):
        if command == "clean":
            return {"start": {"cleaning"}, "resume": {"cleaning"},
                    "pause": {"paused"}, "stop": {"idle"}}.get(data.get("act"), set())
        if command == "charge" and data.get("act") == "go":
            return {"returning", "docked"}
        return set()

    async def _refresh_after_write(self, robot):
        """Read fresh base state without recursing into the command lock."""
        try:
            async with asyncio.timeout(20):
                snapshot = await self.client.snapshot(robot)
        except (CloudError, TimeoutError):
            self._observed.pop(robot.did, None)
            return None
        self._remember(robot, snapshot)
        self.async_set_updated_data((self.data or {}) | {robot.did: snapshot})
        return snapshot

    async def execute(self, robot, command, data, *, expected_map_id=None, expected_generation=None):
        """Bounded FIFO lock, quiet interval, and duplicate-success coalescing.

        Lock covers write, confirmation and refresh. Failures are never retried.
        Distinct queued commands preserve order; overflow is a clear busy error.
        """
        state = self.commands[robot.did]
        if state.pending >= MAX_PENDING:
            raise HomeAssistantError("Yeedi busy; too many pending commands")
        data = dict(data)
        if expected_generation is None:
            expected_generation = self.spatial[robot.did].room_generation
        key = (command, tuple(sorted(data.items())), expected_map_id,
               expected_generation if data.get("type") == "spotArea" else None)
        state.pending += 1
        try:
            async with state.lock:
                if self._already_done(robot, command, data):
                    return "noop"
                elapsed = time.monotonic() - state.last_end
                if elapsed < COMMAND_GAP and not (key == state.last_key and state.last_confirmation):
                    await asyncio.sleep(COMMAND_GAP - elapsed)
                if command == "clean" and data.get("type") == "spotArea":
                    await self._validate_room_command(robot, data, expected_map_id, expected_generation)
                if key == state.last_key and elapsed < COMMAND_GAP and state.last_confirmation:
                    return state.last_confirmation
                state.last_key = None
                state.last_confirmation = None
                self._observed.pop(robot.did, None)
                try:
                    try:
                        # Client bounds each HTTP request, including authentication.
                        await self.client.command(robot, command, data, writing=True)
                        confirmation = "device"
                    except (CommandUncertain, TimeoutError):
                        snapshot = await self._refresh_after_write(robot)
                        expected = self._expected(command, data)
                        if not snapshot or not snapshot.get("online") or snapshot.get("activity") not in expected:
                            raise HomeAssistantError("Yeedi command outcome unknown; check robot before repeating") from None
                        confirmation = "status"
                    if confirmation == "device":
                        snapshot = await self._refresh_after_write(robot)
                        expected = self._expected(command, data)
                        if expected and (not snapshot or snapshot.get("activity") not in expected):
                            # A device ACK may precede its status transition. Such a
                            # snapshot must not suppress the next queued command.
                            self._observed.pop(robot.did, None)
                    state.last_key = key
                    state.last_confirmation = confirmation
                    return confirmation
                finally:
                    state.last_end = time.monotonic()
        except (InvalidAuth, VerificationRequired):
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Yeedi login expired; please reauthenticate") from None
        except RateLimited:
            raise HomeAssistantError("Yeedi busy or rate limited; wait before sending another command") from None
        except DeviceOffline:
            raise HomeAssistantError("Yeedi robot offline or not responding") from None
        except CommandRejected:
            raise HomeAssistantError("Yeedi command explicitly rejected") from None
        except CloudError:
            raise HomeAssistantError("Yeedi command was not confirmed; check robot and connection") from None
        finally:
            state.pending -= 1
