"""Original synthetic legacy-probe tests; no copied or live fixtures."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max import coordinator as module
from custom_components.yeedi_vac_max.client import (
    YeediClient, Robot, CommandTimeout, CommandRejected, CloudError,
    DeviceOffline, InvalidAuth, RateLimited, LEGACY_PROBE_TIMEOUT,
)

ROBOT = Robot("SECRET_ID", "SECRET_RESOURCE", "SECRET_NAME")


def client():
    c = YeediClient(None, "SECRET_ACCOUNT", "SECRET_PASSWORD", "DE", "SECRET_CLIENT")
    c.authenticate = AsyncMock()
    c._request = AsyncMock(return_value={"ret": "ok", "resp": {"body": {
        "data": {"state": "SECRET_STATE", "mid": "SECRET_MAP", "value": "SECRET_MAP_DATA",
                 "SECRET_FIELD": "SECRET", "name": "SECRET_ROOM"}}}})
    return c


async def test_timeout_probes_once_then_backoff(coordinator, monkeypatch):
    now = [10000.]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    coordinator.client.maps.side_effect = CommandTimeout("synthetic")
    await coordinator._spatial_refresh(coordinator.robots[0])
    coordinator.client.probe_legacy_maps.assert_awaited_once_with(coordinator.robots[0])
    coordinator.client.rooms.assert_not_awaited()
    state = coordinator.spatial["vac"]
    assert not state.metadata_valid and not state.rooms_valid and not state.active_map
    assert state.next_map_refresh == 10180
    now[0] += 60
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert coordinator.client.maps.await_count == 1
    assert coordinator.client.probe_legacy_maps.await_count == 1


@pytest.mark.parametrize("error", [None, TimeoutError(), CloudError("synthetic"), CommandRejected("synthetic")])
async def test_only_client_timeout_triggers_probe(coordinator, error):
    coordinator.client.maps.side_effect = error
    await coordinator._spatial_refresh(coordinator.robots[0])
    coordinator.client.probe_legacy_maps.assert_not_awaited()


async def test_single_attempt_payloads_and_safe_structure(caplog):
    c = client()
    await c.probe_legacy_maps(ROBOT)
    calls = c._request.call_args_list
    assert [call.kwargs["json"]["cmdName"] for call in calls] == ["getMapState", "getMajorMap"]
    for call in calls:
        assert call.kwargs["retry"] is False
        assert call.kwargs["json"]["payload"]["body"]["data"] == {}
    result = c.structure_diagnostics(ROBOT)
    for name in ("getMapState", "getMajorMap"):
        assert result[name]["command_success"]
        fields = result[name]["levels"]["resp.body.data"]
        assert fields["state_present"] and fields["state_type"] == "string"
        assert fields["mid_present"] and fields["mid_type"] == "string"
    assert "SECRET" not in json.dumps(result) + caplog.text


@pytest.mark.parametrize("error", [CommandTimeout, CommandRejected])
async def test_first_probe_failure_still_allows_second_without_retry(error):
    c = client()
    successful = c._request.return_value
    c._request.side_effect = [error("SECRET"), successful]
    await c.probe_legacy_maps(ROBOT)
    assert c._request.await_count == 2
    assert not c.structure_diagnostics(ROBOT)["getMapState"]["command_success"]
    assert c.structure_diagnostics(ROBOT)["getMajorMap"]["command_success"]


@pytest.mark.parametrize("error", [RateLimited, DeviceOffline, InvalidAuth])
async def test_backpressure_stops_probe_and_clears_previous_result(error):
    c = client()
    await c.probe_legacy_maps(ROBOT)
    c._request.reset_mock()
    c._request.side_effect = error("SECRET")
    await c.probe_legacy_maps(ROBOT)
    assert c._request.await_count == 1
    assert c.structure_diagnostics(ROBOT)["getMajorMap"] == {"attempted": False}


async def test_probes_sequential_and_bounded():
    c = client()
    entered, release = asyncio.Event(), asyncio.Event()
    async def request(*args, **kwargs):
        entered.set()
        await release.wait()
        return {"ret":"ok", "resp":{"body":{"data":{}}}}
    c._request.side_effect = request
    task = asyncio.create_task(c.probe_legacy_maps(ROBOT))
    await entered.wait()
    assert c._request.await_count == 1
    release.set()
    await task
    assert c._request.await_count == 2
    assert LEGACY_PROBE_TIMEOUT == 18


async def test_cancellation_propagates_no_second_probe():
    c = client()
    c._request.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await c.probe_legacy_maps(ROBOT)
    assert c._request.await_count == 1


async def test_writes_never_trigger_probe(coordinator):
    coordinator.client.command.side_effect = CommandTimeout("synthetic")
    coordinator.client.snapshot.return_value = {"online":True, "activity":"cleaning"}
    await coordinator.execute(coordinator.robots[0], "clean", {"act":"start"})
    coordinator.client.probe_legacy_maps.assert_not_awaited()


async def test_legacy_write_disallowed_before_network():
    c = client()
    with pytest.raises(ValueError):
        await c.command(ROBOT, "getMajorMap", writing=True)
    c._request.assert_not_awaited()
