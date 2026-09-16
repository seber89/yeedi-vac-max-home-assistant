"""Central base/spatial state and serialized, never-retried device writes."""
import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
import time

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (CloudError, InvalidAuth, VerificationRequired, CommandUncertain,
                     DeviceOffline, RateLimited, CommandRejected)
from .map_data import YeediMap, YeediRoom, RobotPosition, DockPosition

_LOGGER = logging.getLogger(__name__)
MAP_INTERVAL = 3600
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

    async def _spatial_refresh(self, robot, *, force=False):
        state = self.spatial[robot.did]
        try:
            async with asyncio.timeout(8):
                state.robot_position, state.dock_position = await self.client.positions(robot)
        except (CloudError, TimeoutError):
            state.robot_position = state.dock_position = None
        if not force and time.monotonic() < state.next_map_refresh:
            return
        state.next_map_refresh = time.monotonic() + MAP_INTERVAL
        try:
            async with asyncio.timeout(20):
                maps = await self.client.maps(robot)
                active = [m for m in maps if m.active]
                selected = active[0] if len(active) == 1 else None
                if selected != state.active_map:
                    state.rooms = ()
                state.maps, state.active_map = maps, selected
                state.metadata_valid = True
                state.rooms_valid = False
                if selected is None:
                    state.rooms = ()
                    return
                state.rooms = await self.client.rooms(robot, selected.map_id)
                state.rooms_valid = True
        except (CloudError, TimeoutError):
            state.metadata_valid = False
            state.rooms_valid = False
            # Retain cache but mark stale; future room commands must require validity.

    async def async_refresh_map_data(self, robot):
        """Explicit refresh hook; reload creates fresh caches automatically."""
        async with self.commands[robot.did].lock:
            await self._spatial_refresh(robot, force=True)
        self.async_update_listeners()

    async def _poll_robot(self, robot):
        async with self.commands[robot.did].lock:
            async with asyncio.timeout(60):
                base = await self.client.snapshot(robot)
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
            return None
        self.async_set_updated_data((self.data or {}) | {robot.did: snapshot})
        return snapshot

    async def execute(self, robot, command, data):
        """Bounded FIFO lock, quiet interval, and duplicate-success coalescing.

        Lock covers write, confirmation and refresh. Failures are never retried.
        Distinct queued commands preserve order; overflow is a clear busy error.
        """
        state = self.commands[robot.did]
        if state.pending >= MAX_PENDING:
            raise HomeAssistantError("Yeedi busy; too many pending commands")
        data = dict(data)
        key = (command, tuple(sorted(data.items())))
        state.pending += 1
        try:
            async with state.lock:
                elapsed = time.monotonic() - state.last_end
                if key == state.last_key and elapsed < COMMAND_GAP and state.last_confirmation:
                    return state.last_confirmation
                if elapsed < COMMAND_GAP:
                    await asyncio.sleep(COMMAND_GAP - elapsed)
                state.last_key = None
                state.last_confirmation = None
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
                        await self._refresh_after_write(robot)
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
