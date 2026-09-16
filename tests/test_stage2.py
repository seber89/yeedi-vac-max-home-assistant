"""Synthetic native room cleaning and no-op regression tests."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.vacuum import Segment, VacuumEntityFeature
from homeassistant.exceptions import HomeAssistantError

from test_coordinator import coordinator
from custom_components.yeedi_vac_max.client import CommandRejected, CommandUncertain, CommandTimeout, CloudError
from custom_components.yeedi_vac_max.map_data import YeediMap, YeediRoom
from custom_components.yeedi_vac_max.vacuum import YeediVacuum


def setup_rooms(c):
    state = c.spatial["vac"]
    state.active_map = YeediMap("map-a", None, True)
    state.rooms = tuple(YeediRoom(i, "Synthetic " + i) for i in ("3", "4", "7"))
    state.metadata_valid = state.rooms_valid = True
    state.next_map_refresh = time.monotonic() + 3600
    c.client.maps.return_value = (state.active_map,)
    return YeediVacuum(c, c.robots[0])


async def test_native_segments_and_capability(coordinator):
    v = setup_rooms(coordinator)
    assert v.supported_features & VacuumEntityFeature.CLEAN_AREA
    assert await v.async_get_segments() == [Segment(id=i, name="Synthetic " + i, group="map-a") for i in ("3", "4", "7")]
    coordinator.client.rooms.assert_not_awaited()
    coordinator.spatial["vac"].rooms = ()
    assert not v.supported_features & VacuumEntityFeature.CLEAN_AREA
    assert v.supported_features & VacuumEntityFeature.START


@pytest.mark.parametrize("ids,content", [(["3"], "3"), (["3", "4"], "3,4"),
    (["3", "4", "7"], "3,4,7"), ([3, " 4 ", "3", "7", 4], "3,4,7")])
async def test_room_payload_and_central_queue(coordinator, ids, content):
    v = setup_rooms(coordinator)
    original = coordinator.execute
    coordinator.execute = AsyncMock(wraps=original)
    await v.async_clean_segments(ids)
    coordinator.execute.assert_awaited_once()
    coordinator.client.command.assert_awaited_once_with(coordinator.robots[0], "clean",
        {"act": "start", "type": "spotArea", "content": content,
         "count": 1, "donotClean": 0, "router": "plan"}, writing=True)


@pytest.mark.parametrize("ids", [[], ["unknown"], ["3,4"], [True], [None], [3.0], "3", ["3", "99"]])
async def test_invalid_selection_never_writes(coordinator, ids):
    v = setup_rooms(coordinator)
    with pytest.raises(HomeAssistantError):
        await v.async_clean_segments(ids)
    coordinator.client.command.assert_not_awaited()


@pytest.mark.parametrize("field,value", [("rooms_valid", False), ("metadata_valid", False),
    ("next_map_refresh", 0), ("active_map", None), ("rooms", (YeediRoom("", "Synthetic"),))])
async def test_unusable_cache_hides_capability(coordinator, field, value):
    v = setup_rooms(coordinator)
    setattr(coordinator.spatial["vac"], field, value)
    assert not v.supported_features & VacuumEntityFeature.CLEAN_AREA
    with pytest.raises(HomeAssistantError):
        await v.async_clean_segments(["3"])


async def test_map_change_blocks_old_selection_and_reloads(coordinator):
    v = setup_rooms(coordinator)
    coordinator.client.maps.return_value = (YeediMap("map-b", None, True),)
    coordinator.client.rooms.return_value = (YeediRoom("8", "Synthetic new"),)
    with pytest.raises(HomeAssistantError, match="map changed"):
        await v.async_clean_segments(["3"])
    coordinator.client.command.assert_not_awaited()
    assert [r.room_id for r in coordinator.rooms["vac"]] == ["8"]
    assert coordinator.spatial["vac"].active_map.map_id == "map-b"


async def test_map_check_failure_does_not_write(coordinator):
    v = setup_rooms(coordinator)
    coordinator.client.maps.side_effect = CloudError("synthetic")
    with pytest.raises(HomeAssistantError):
        await v.async_clean_segments(["3"])
    coordinator.client.command.assert_not_awaited()
    assert not coordinator.rooms["vac"]


@pytest.mark.parametrize("error", [CommandUncertain, CommandTimeout])
async def test_room_unclear_cleaning_confirms_start_only(coordinator, error):
    v = setup_rooms(coordinator)
    coordinator.client.command.side_effect = error("synthetic")
    coordinator.client.snapshot.return_value = {"online": True, "activity": "cleaning"}
    await v.async_clean_segments(["3"])
    assert coordinator.commands["vac"].last_confirmation == "status"
    assert coordinator.client.command.await_count == 1


async def test_room_explicit_reject_and_timeout_mismatch(coordinator, monkeypatch):
    monkeypatch.setattr("custom_components.yeedi_vac_max.coordinator.COMMAND_GAP", 0)
    v = setup_rooms(coordinator)
    for error in (CommandRejected, CommandTimeout):
        coordinator.client.command.side_effect = error("synthetic")
        with pytest.raises(HomeAssistantError):
            await v.async_clean_segments(["3"])
    assert coordinator.client.command.await_count == 2


@pytest.mark.parametrize("selections,expected", [([["3"], ["3"]], ["3"]),
    ([["3"], ["4"], ["3"]], ["3", "4", "3"])])
async def test_spotarea_serialization(coordinator, monkeypatch, selections, expected):
    monkeypatch.setattr("custom_components.yeedi_vac_max.coordinator.COMMAND_GAP", .01)
    v = setup_rooms(coordinator)
    calls, active = [], 0
    async def write(robot, command, data, **kwargs):
        nonlocal active
        active += 1
        assert active == 1
        calls.append(data["content"])
        await asyncio.sleep(.01)
        active -= 1
    coordinator.client.command.side_effect = write
    coordinator.client.snapshot.return_value = {"online": True, "activity": "cleaning"}
    await asyncio.gather(*(v.async_clean_segments(ids) for ids in selections))
    assert calls == expected


@pytest.mark.parametrize("activity,method", [("docked", "async_return_to_base"),
    ("returning", "async_return_to_base"), ("paused", "async_pause"),
    ("cleaning", "async_start"), ("idle", "async_stop"), ("docked", "async_stop")])
async def test_redundant_noops(coordinator, activity, method):
    v = setup_rooms(coordinator)
    snapshot = {"online": True, "activity": activity}
    coordinator.data = {"vac": snapshot}
    coordinator._remember(coordinator.robots[0], snapshot)
    await getattr(v, method)()
    coordinator.client.command.assert_not_awaited()


@pytest.mark.parametrize("activity,method", [(None, "async_start"), ("idle", "async_start"),
    ("paused", "async_start"), ("cleaning", "async_pause"), ("cleaning", "async_stop"),
    ("cleaning", "async_return_to_base")])
async def test_legitimate_transitions(coordinator, activity, method):
    v = setup_rooms(coordinator)
    snapshot = {"online": True, "activity": activity}
    coordinator.data = {"vac": snapshot}
    coordinator._remember(coordinator.robots[0], snapshot)
    await getattr(v, method)()
    assert coordinator.client.command.await_count == 1


async def test_stale_noop_does_not_block(coordinator):
    v = setup_rooms(coordinator)
    coordinator._observed["vac"] = (time.monotonic() - 100, {"online": True, "activity": "docked"})
    await v.async_return_to_base()
    assert coordinator.client.command.await_count == 1


async def test_same_ids_on_different_map_require_remapping(coordinator):
    v = setup_rooms(coordinator)
    v.registry_entry = SimpleNamespace(options={"vacuum": {"last_seen_segments": [
        {"id": i, "name": "Synthetic " + i, "group": "old-map"} for i in ("3", "4", "7")]}})
    from unittest.mock import Mock
    v.async_create_segments_issue = Mock()
    with pytest.raises(HomeAssistantError, match="mapping changed"):
        await v.async_clean_segments(["3"])
    coordinator.client.command.assert_not_awaited()
    v.async_create_segments_issue.assert_called_once()
