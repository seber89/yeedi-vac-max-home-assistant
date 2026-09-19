"""Synthetic fixtures reflecting only owner-reported legacy field structure."""
import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max.client import (
    YeediClient, Robot, CloudError, CommandTimeout, CommandRejected,
    MAP_DISCOVERY_TIMEOUT, MAP_REQUEST_TIMEOUT, LEGACY_PROBE_TIMEOUT,
)
from custom_components.yeedi_vac_max.coordinator import ROOM_REFRESH_TIMEOUT
from custom_components.yeedi_vac_max.map_data import YeediMap, YeediRoom
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

ROBOT = Robot("SYNTHETIC_DEVICE", "SYNTHETIC_RESOURCE", "SYNTHETIC_NAME")


def envelope(data):
    return {"ret":"ok", "resp":{"body":{"data":data}}}


def client(major=None, room=None):
    c = YeediClient(None, "PRIVATE_ACCOUNT", "PRIVATE_PASSWORD", "DE", "PRIVATE_CLIENT")
    c.authenticate = AsyncMock()
    c.positions = AsyncMock(return_value=(None, None))
    c.load_raw_map = AsyncMock(return_value=None)  # Independently tested Beta-6 loader.
    c._request = AsyncMock(side_effect=[CommandTimeout("synthetic"),
        envelope({"state":"arbitrary_uninterpreted_string"}),
        envelope(major if major is not None else {"mid":"PRIVATE_MAP", "value":"PRIVATE_MAP_DATA"}),
        envelope(room if room is not None else {"subsets":[]})])
    return c


async def test_primary_success_skips_legacy():
    c = client()
    c._request.side_effect = [envelope({"info":[{"mid":"known", "using":1}]})]
    assert await c.maps(ROBOT) == (YeediMap("known", None, True),)
    assert c._request.await_count == 1


async def test_timeout_legacy_returns_only_current_candidate():
    c = client()
    assert await c.maps(ROBOT) == (YeediMap("PRIVATE_MAP", None, True),)
    assert [v.kwargs["json"]["cmdName"] for v in c._request.call_args_list] == [
        "getCachedMapInfo", "getMapState", "getMajorMap"]


@pytest.mark.parametrize("mid", [None, "0", " 0 ", "", "   ", "x"*129, 123, False, {}, []])
async def test_invalid_legacy_id_fails(mid):
    c = client(major={"mid":mid, "value":"PRIVATE_MAP_DATA"})
    with pytest.raises(CloudError):
        await c.maps(ROBOT)


async def test_missing_mid_fails():
    with pytest.raises(CloudError):
        await client(major={"value":"PRIVATE_MAP_DATA"}).maps(ROBOT)


async def test_major_value_never_accessed():
    class GuardedData(dict):
        def get(self, key, *args):
            assert key != "value"
            return super().get(key, *args)
        def __getitem__(self, key):
            assert key != "value"
            return super().__getitem__(key)
    c = client()
    c.command = AsyncMock(side_effect=[CommandTimeout("synthetic"),
        {"data":{"state":"ignored"}}, {"data":GuardedData(mid="valid", value="opaque")}])
    assert await c.maps(ROBOT) == (YeediMap("valid", None, True),)


async def test_legacy_map_immediately_reads_rooms_and_safe_diagnostics(coordinator, caplog):
    room = {"subsets":[{"mssid":"PRIVATE_ROOM_ID", "name":"PRIVATE_ROOM_NAME",
                        "subtype":"PRIVATE_SUBTYPE", "value":"PRIVATE_POLYGON", "compress":1}]}
    c = client(room=room)
    coordinator.client = c
    await coordinator._spatial_refresh(coordinator.robots[0])
    state = coordinator.spatial["vac"]
    assert state.metadata_valid and state.rooms_valid
    assert state.active_map == YeediMap("PRIVATE_MAP", None, True)
    assert len(coordinator.rooms["vac"]) == 1
    calls = c._request.call_args_list
    assert len(calls) == 4  # No forced getMapSubSet probe.
    assert calls[-1].kwargs["json"]["cmdName"] == "getMapSet"
    assert calls[-1].kwargs["json"]["payload"]["body"]["data"] == {"mid":"PRIVATE_MAP", "type":"ar"}
    result = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=coordinator))
    assert "PRIVATE" not in json.dumps(result) + caplog.text


async def test_room_failure_keeps_map_but_exposes_no_rooms(coordinator):
    c = client(room={"unexpected": []})
    coordinator.client = c
    coordinator.spatial["vac"].rooms = (YeediRoom("old", "old"),)
    await coordinator._spatial_refresh(coordinator.robots[0])
    state = coordinator.spatial["vac"]
    assert state.metadata_valid and state.active_map.map_id == "PRIVATE_MAP"
    assert not state.rooms_valid and not coordinator.rooms["vac"] and not state.rooms
    assert 170 < state.next_map_refresh - time.monotonic() <= 180


async def test_room_preflight_uses_same_legacy_discovery(coordinator):
    c = client(room={"subsets":[{"mssid":"3", "name":"Synthetic", "value":"opaque"}]})
    coordinator.client = c
    state = coordinator.spatial["vac"]
    state.active_map = YeediMap("PRIVATE_MAP", None, True)
    state.metadata_valid = state.rooms_valid = True
    state.rooms = (YeediRoom("3", "Synthetic"),)
    state.next_map_refresh = time.monotonic() + 3600
    await coordinator._validate_room_command(coordinator.robots[0], {"content":"3"}, "PRIVATE_MAP", state.room_generation)
    assert c._request.await_count == 4  # Also revalidate the current room generation.


async def test_room_retry_completes_beyond_old_outer_budget(coordinator, monkeypatch):
    sleep, timeout = asyncio.sleep, asyncio.timeout
    c = client()
    c.maps = AsyncMock(return_value=(YeediMap("known", None, True),))
    calls = []
    class Request:
        async def __aenter__(self):
            await sleep(.15)
            if len(calls) == 1:
                raise TimeoutError
            return SimpleNamespace(status=200, json=AsyncMock(return_value=envelope({"subsets":[]})))
        async def __aexit__(self, *args):
            pass
    def request(*args, **kwargs):
        calls.append(kwargs)
        return Request()
    c._request = YeediClient._request.__get__(c)
    c.session = SimpleNamespace(request=request)
    coordinator.client = c
    monkeypatch.setattr(asyncio, "sleep", lambda seconds:sleep(seconds/100))
    monkeypatch.setattr(asyncio, "timeout", lambda seconds:timeout(seconds/100))
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert len(calls) == 2 and coordinator.spatial["vac"].rooms_valid
    assert ROOM_REFRESH_TIMEOUT == 40
    assert MAP_REQUEST_TIMEOUT == 40
    assert MAP_DISCOVERY_TIMEOUT > MAP_REQUEST_TIMEOUT + 2 * LEGACY_PROBE_TIMEOUT


async def test_rejection_does_not_fall_back():
    c = client()
    c._request.side_effect = CommandRejected("synthetic")
    with pytest.raises(CommandRejected):
        await c.maps(ROBOT)
    assert c._request.await_count == 1
