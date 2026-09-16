"""Original synthetic cases only; no captured household data or copied fixtures."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from test_coordinator import coordinator
from custom_components.yeedi_vac_max.client import (
    YeediClient, Robot, CloudError, CommandUncertain, CommandRejected,
    CommandTimeout, RateLimited, DeviceOffline, CannotConnect, command_body,
)
from custom_components.yeedi_vac_max.map_data import (
    YeediMap, YeediRoom, RobotPosition, DockPosition, polygon, position, fallback_name,
)
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

ROBOT = Robot("synthetic-device", "synthetic-resource", "Synthetic")


@pytest.mark.parametrize("command,data,activity", [
    ("clean", {"act": "start"}, "cleaning"),
    ("clean", {"act": "resume"}, "cleaning"),
    ("clean", {"act": "pause"}, "paused"),
    ("clean", {"act": "stop"}, "idle"),
    ("charge", {"act": "go"}, "returning"),
    ("charge", {"act": "go"}, "docked"),
])
async def test_status_confirmation(coordinator, command, data, activity):
    coordinator.client.command.side_effect = CommandUncertain("uncertain")
    coordinator.client.snapshot.return_value = {"online": True, "activity": activity}
    assert await coordinator.execute(coordinator.robots[0], command, data) == "status"
    assert coordinator.client.command.await_count == 1


async def test_direct_start_and_failed_refresh(coordinator):
    coordinator.client.snapshot.side_effect = CloudError("failed")
    assert await coordinator.execute(coordinator.robots[0], "clean", {"act": "start"}) == "device"
    assert coordinator.client.command.await_count == 1


@pytest.mark.parametrize("error", [CommandRejected, RateLimited, DeviceOffline])
async def test_explicit_errors_never_status_confirm(coordinator, error):
    coordinator.client.command.side_effect = error("safe")
    coordinator.client.snapshot.return_value = {"online": True, "activity": "cleaning"}
    with pytest.raises(HomeAssistantError):
        await coordinator.execute(coordinator.robots[0], "clean", {"act": "start"})
    coordinator.client.snapshot.assert_not_awaited()


@pytest.mark.parametrize("snapshot", [
    {"online": True, "activity": "idle"},
    {"online": False, "activity": "cleaning"},
    {"online": True, "activity": None},
])
async def test_timeout_mismatch_never_retries(coordinator, snapshot):
    coordinator.client.command.side_effect = CommandTimeout("timeout")
    coordinator.client.snapshot.return_value = snapshot
    with pytest.raises(HomeAssistantError, match="outcome unknown"):
        await coordinator.execute(coordinator.robots[0], "clean", {"act": "start"})
    assert coordinator.client.command.await_count == 1


async def test_confirmation_failure_preserves_availability(coordinator):
    coordinator.last_update_success = True
    coordinator.data = {"vac": {"online": True, "activity": "idle"}}
    coordinator.client.command.side_effect = CommandUncertain("uncertain")
    coordinator.client.snapshot.side_effect = CloudError("failed")
    with pytest.raises(HomeAssistantError):
        await coordinator.execute(coordinator.robots[0], "clean", {"act": "start"})
    assert coordinator.last_update_success
    assert coordinator.data["vac"]["activity"] == "idle"


@pytest.mark.parametrize("actions,expected", [
    (["start", "start"], ["start"]),
    (["stop", "stop"], ["stop"]),
    (["go", "go"], ["go"]),
    (["start", "stop", "start"], ["start", "stop", "start"]),
])
async def test_serialized_clicks(coordinator, monkeypatch, actions, expected):
    monkeypatch.setattr("custom_components.yeedi_vac_max.coordinator.COMMAND_GAP", .01)
    active = 0
    seen = []
    async def write(robot, command, data, **kwargs):
        nonlocal active
        active += 1
        assert active == 1
        seen.append(data["act"])
        await asyncio.sleep(.01)
        active -= 1
    coordinator.client.command.side_effect = write
    await asyncio.gather(*(coordinator.execute(coordinator.robots[0],
        "charge" if act == "go" else "clean", {"act": act}) for act in actions))
    assert seen == expected
    assert coordinator.commands["vac"].pending == 0


async def test_bounded_queue_and_cancellation(coordinator):
    started, release = asyncio.Event(), asyncio.Event()
    async def write(*args, **kwargs):
        started.set()
        await release.wait()
    coordinator.client.command.side_effect = write
    task = asyncio.create_task(coordinator.execute(coordinator.robots[0], "clean", {"act": "start"}))
    await started.wait()
    waiting = [asyncio.create_task(coordinator.execute(coordinator.robots[0], "clean", {"act": "stop"})) for _ in range(3)]
    await asyncio.sleep(0)
    with pytest.raises(HomeAssistantError, match="busy"):
        await coordinator.execute(coordinator.robots[0], "clean", {"act": "pause"})
    for item in waiting:
        item.cancel()
    await asyncio.gather(*waiting, return_exceptions=True)
    release.set()
    await task
    assert coordinator.commands["vac"].pending == 0


async def test_optional_data_errors_and_cache(coordinator):
    coordinator.client.maps.return_value = (YeediMap("synthetic-map", "private", True),)
    coordinator.client.rooms.return_value = (YeediRoom("7", "private room"),)
    await coordinator._async_update_data()
    await coordinator._async_update_data()
    assert coordinator.client.maps.await_count == 1
    assert coordinator.client.positions.await_count == 2
    coordinator.client.maps.side_effect = CloudError("safe")
    coordinator.client.positions.side_effect = CloudError("safe")
    await coordinator.async_refresh_map_data(coordinator.robots[0])
    assert not coordinator.spatial["vac"].metadata_valid
    assert (await coordinator._async_update_data())["vac"]["online"]


async def test_no_unique_active_map_clears_rooms(coordinator):
    state = coordinator.spatial["vac"]
    state.rooms = (YeediRoom("1", "private"),)
    coordinator.client.maps.return_value = (YeediMap("a", None, True), YeediMap("b", None, True))
    await coordinator._async_update_data()
    assert state.active_map is None and state.rooms == ()
    coordinator.client.rooms.assert_not_awaited()


async def test_diagnostics_only_flags(coordinator):
    state = coordinator.spatial["vac"]
    state.active_map = YeediMap("secret-map", "secret-name", True)
    state.rooms = (YeediRoom("secret-room", "secret-name", polygon=((1., 2.), (3., 4.), (5., 6.))),)
    state.robot_position = RobotPosition(98765, 43210)
    result = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=coordinator))
    assert all(isinstance(v, bool) for v in result["robots"][0].values())
    assert "secret" not in str(result) and "98765" not in str(result)


def test_polygon_and_positions_defensive():
    assert polygon("0,0;2,0;2,2") == ((0., 0.), (2., 0.), (2., 2.))
    assert polygon("0,0;2,0;broken,2") is None
    assert polygon("[[0,0],[2,0],[2,2]]") == ((0., 0.), (2., 0.), (2., 2.))
    for value in ("compressed", "{}", [[0,0]], [[0,0],[1,0],[float("nan"),2]]):
        assert polygon(value) is None
    assert polygon("[[0,0],[2,0],[2,2]]", 1) is None
    assert position({"x": 0, "y": "2", "a": 90}, RobotPosition) == RobotPosition(0, 2, 90)
    for value in (None, {}, {"x": True, "y": 1}, {"x": "NaN", "y": 1}, {"x": 1, "y": 2, "invalid": 1}):
        assert position(value, DockPosition) is None
    assert fallback_name(26) == "Raum AA"


async def test_v1_reads_and_room_fallbacks():
    client = YeediClient(None, "synthetic", "synthetic", "DE", "synthetic")
    client.command = AsyncMock(side_effect=[
        {"data": {"info": [{"mid": "0", "using": 1}, {"mid": "a", "using": 1}]}},
        {"data": {"mid": "a", "subsets": [{"mssid": 0}, {"mssid": "9"}, {}]}},
        {"data": {"mssid": 0, "name": "Synthetic room", "compress": 1, "value": "unknown"}},
        CloudError("unavailable"),
        {"data": {"deebotPos": {"x": 0, "y": 3}, "chargePos": [{"x": 1, "y": 2}]}},
    ])
    assert await client.maps(ROBOT) == (YeediMap("a", None, True),)
    assert await client.rooms(ROBOT, "a") == (YeediRoom("0", "Synthetic room"), YeediRoom("9", "Raum B"))
    assert await client.positions(ROBOT) == (RobotPosition(0, 3), DockPosition(1, 2))
    assert client.command.call_args_list[1].args[2] == {"mid": "a", "type": "ar"}
    assert client.command.call_args_list[-1].args[2] == ["chargePos", "deebotPos"]


@pytest.mark.parametrize("response,error", [
    ({"ret": "ok", "resp": {"body": {}}}, CommandUncertain),
    ({"ret": "fail", "errno": 123}, CommandRejected),
    ({"ret": "ok", "resp": {"body": {"code": 4}}}, CommandRejected),
])
def test_acknowledgement_categories(response, error):
    with pytest.raises(error):
        command_body(response, writing=True)


async def test_login_transport_failure_is_not_status_confirmed(coordinator):
    coordinator.client.command.side_effect = CannotConnect("login failed before write")
    coordinator.client.snapshot.return_value = {"online": True, "activity": "cleaning"}
    with pytest.raises(HomeAssistantError):
        await coordinator.execute(coordinator.robots[0], "clean", {"act": "start"})
    coordinator.client.snapshot.assert_not_awaited()


async def test_lock_includes_confirmation_read(coordinator, monkeypatch):
    monkeypatch.setattr("custom_components.yeedi_vac_max.coordinator.COMMAND_GAP", 0)
    entered, release = asyncio.Event(), asyncio.Event()
    async def snapshot(*args):
        entered.set()
        await release.wait()
        return {"online": True, "activity": "idle"}
    coordinator.client.snapshot.side_effect = snapshot
    first = asyncio.create_task(coordinator.execute(coordinator.robots[0], "clean", {"act": "start"}))
    await entered.wait()
    second = asyncio.create_task(coordinator.execute(coordinator.robots[0], "clean", {"act": "stop"}))
    await asyncio.sleep(0)
    assert coordinator.client.command.await_count == 1
    release.set()
    await asyncio.gather(first, second)
    assert coordinator.client.command.await_count == 2


async def test_timeout_matching_status_confirmed_once(coordinator):
    coordinator.client.command.side_effect = CommandTimeout("timeout")
    coordinator.client.snapshot.return_value = {"online": True, "activity": "cleaning"}
    assert await coordinator.execute(coordinator.robots[0], "clean", {"act": "start"}) == "status"
    assert coordinator.client.command.await_count == 1


async def test_room_map_change_drops_old_cache(coordinator):
    state = coordinator.spatial["vac"]
    state.active_map = YeediMap("old", None, True)
    state.rooms = (YeediRoom("old-room", "old-name"),)
    coordinator.client.maps.return_value = (YeediMap("new", None, True),)
    coordinator.client.rooms.side_effect = CloudError("details failed")
    await coordinator.async_refresh_map_data(coordinator.robots[0])
    assert state.active_map.map_id == "new"
    assert not state.rooms and not state.rooms_valid


@pytest.mark.parametrize("data", [{}, {"info": None}, {"info": [{"mid": "x"}, {"mid": "x"}]}])
async def test_invalid_maps(data):
    client = YeediClient(None, "synthetic", "synthetic", "DE", "synthetic")
    client.command = AsyncMock(return_value={"data": data})
    with pytest.raises(CloudError):
        await client.maps(ROBOT)


async def test_read_only_positions_envelope():
    client = YeediClient(None, "synthetic", "synthetic", "DE", "synthetic")
    client.authenticate = AsyncMock()
    client._request = AsyncMock(return_value={"ret": "ok", "resp": {"body": {"data": {}}}})
    assert await client.positions(ROBOT) == (None, None)
    assert client._request.call_args.kwargs["json"]["payload"]["body"]["data"] == ["chargePos", "deebotPos"]


async def test_transport_error_after_write_is_uncertain():
    client = YeediClient(None, "synthetic", "synthetic", "DE", "synthetic")
    client.authenticate = AsyncMock()
    client._request = AsyncMock(side_effect=CannotConnect("transport"))
    with pytest.raises(CommandUncertain):
        await client.command(ROBOT, "clean", {"act": "start"}, writing=True)
    assert client._request.await_count == 1
    assert not client._request.call_args.kwargs["retry"]
