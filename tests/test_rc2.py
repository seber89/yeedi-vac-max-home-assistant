"""Synthetic regressions for the restored functional outline preparation."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max import client as cloud
from custom_components.yeedi_vac_max.map_data import YeediMap, YeediRoom
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

ROBOT = cloud.Robot("PRIVATE_DEVICE", "PRIVATE_RESOURCE", "PRIVATE_NAME")


def client():
    c = cloud.YeediClient(None, "PRIVATE_ACCOUNT", "PRIVATE_PASSWORD", "DE", "PRIVATE_CLIENT")
    c.authenticate = AsyncMock()
    c._request = AsyncMock(return_value={"ret": "ok", "resp": {"body": {
        "data": {"mid": "PRIVATE_MAP", "value": "PRIVATE_PAYLOAD"}}}})
    return c


async def test_exact_read_payload_and_no_response_retention(caplog):
    c = client()
    before = set(vars(c))
    assert await c.prepare_raw_map(ROBOT, "PRIVATE_MAP") is None
    c._request.assert_awaited_once()
    request = c._request.call_args.kwargs
    assert request["retry"] is True
    assert request["json"]["cmdName"] == "getMapInfo"
    assert request["json"]["payload"]["body"]["data"] == {"mid": "PRIVATE_MAP", "type": "ol"}
    assert set(vars(c)) == before
    assert "PRIVATE" not in caplog.text


@pytest.mark.parametrize("mid", [None, "", "0", " 0 ", " padded ", "x"*129, 4, False, {}, []])
async def test_invalid_map_never_requests(mid):
    c = client()
    await c.prepare_raw_map(ROBOT, mid)
    c.authenticate.assert_not_awaited()
    c._request.assert_not_awaited()


@pytest.mark.parametrize("error", [None, cloud.CommandTimeout("PRIVATE"),
                                  cloud.CloudError("PRIVATE"), TimeoutError()])
async def test_spatial_preparation_precedes_raw_and_preserves_rooms(coordinator, error, caplog):
    robot = coordinator.robots[0]
    c = client()
    c.positions = AsyncMock(return_value=(None, None))
    c.maps = AsyncMock(return_value=(YeediMap("PRIVATE_MAP", None, True),))
    c.rooms = AsyncMock(return_value=(YeediRoom("PRIVATE_ROOM", "PRIVATE_ROOM_NAME"),))
    order = []
    async def request(*args, **kwargs):
        order.append("getMapInfo")
        if error is not None:
            raise error
        return {"ret": "ok", "resp": {"body": {"data": {}}}}
    c._request.side_effect = request
    async def load(*args):
        order.append("raw")
        return None
    c.load_raw_map = AsyncMock(side_effect=load)
    coordinator.client = c
    await coordinator._spatial_refresh(robot)
    assert order == ["getMapInfo", "raw"]
    state = coordinator.spatial[robot.did]
    assert state.metadata_valid and state.rooms_valid and state.rooms
    assert coordinator.commands[robot.did].pending == 0
    await coordinator._spatial_refresh(robot)
    assert order == ["getMapInfo", "raw"]  # No extra preparation on cached minute polls.
    c.command = AsyncMock(return_value={})
    c.snapshot = AsyncMock(return_value={"online": True, "activity": "idle"})
    coordinator.async_request_refresh = AsyncMock()
    await coordinator.execute(robot, "clean", {"act": "stop"})
    c.command.assert_awaited_once_with(robot, "clean", {"act": "stop"}, writing=True)
    report = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=coordinator))
    assert not any(key.endswith("_probe") for key in report)
    assert "PRIVATE" not in json.dumps(report) + caplog.text


async def test_outer_deadline_is_bounded_and_cancel_propagates(monkeypatch):
    c = client()
    timeout = asyncio.timeout
    budgets = []
    def scaled(seconds):
        budgets.append(seconds)
        return timeout(.01)
    async def pending(*args, **kwargs):
        await asyncio.Event().wait()
    c.command = AsyncMock(side_effect=pending)
    monkeypatch.setattr(asyncio, "timeout", scaled)
    await c.prepare_raw_map(ROBOT, "map")
    assert budgets == [cloud.MAP_REQUEST_TIMEOUT]
    assert cloud.READ_RETRY_BUDGET < budgets[0] <= 40
    c.command.assert_awaited_once()
    c.command.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await c.prepare_raw_map(ROBOT, "map")


async def test_no_active_map_no_preparation(coordinator):
    await coordinator._spatial_refresh(coordinator.robots[0])
    coordinator.client.prepare_raw_map.assert_not_awaited()


async def test_get_map_info_write_still_forbidden():
    c = client()
    with pytest.raises(ValueError):
        await c.command(ROBOT, "getMapInfo", writing=True)
    c.authenticate.assert_not_awaited()
