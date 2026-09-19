"""Synthetic response validation and compact diagnostics privacy regressions."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.yeedi_vac_max.client import (
    YeediClient, Robot, CloudError, CommandRejected, CommandTimeout,
    DeviceOffline, RateLimited, CannotConnect,
)
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics
from custom_components.yeedi_vac_max.coordinator import SpatialState, CommandState

ROBOT = Robot("PRIVATE_DEVICE", "PRIVATE_RESOURCE", "PRIVATE_NAME")


def client(response=None):
    result = YeediClient(None, "PRIVATE_EMAIL", "PRIVATE_PASSWORD", "DE", "PRIVATE_ID")
    result.authenticate = AsyncMock()
    result._device_request = AsyncMock(return_value=response)
    return result


@pytest.mark.parametrize("encoded", [False, True])
async def test_safe_structure_end_to_end(encoded, caplog):
    data = {"info": [{"mid": "PRIVATE_MAP", "using": 1, "name": "PRIVATE_ROOM"}],
            "subsets": [{"mssid": "PRIVATE_ROOM_ID", "msid": "PRIVATE_SET"}],
            "deebotPos": {"x": 9876543, "y": -9876543},
            "chargePos": [{"x": 1234567, "y": 7654321}],
            "PRIVATE_UNKNOWN_KEY": "PRIVATE_TOKEN", "value": "PRIVATE_POLYGON"}
    payload = {"body": {"data": data, "code": 0}}
    c = client({"ret": "ok", "resp": json.dumps(payload) if encoded else payload})
    await c.command(ROBOT, "getCachedMapInfo")
    coordinator = SimpleNamespace(client=c, robots=[ROBOT], data={},
        spatial={ROBOT.did: SpatialState()}, commands={ROBOT.did: CommandState()},
        last_update_success=True)
    output = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=coordinator))
    text = json.dumps(output) + caplog.text
    for secret in ("PRIVATE", "9876543", "1234567", "7654321"):
        assert secret not in text
    assert not any(key.endswith("_probe") for key in output)
    c.close()


@pytest.mark.parametrize("where", ["resp", "body", "data"])
async def test_locations_observed_not_accepted_as_parser_fallback(where):
    info = {"info": [{"mid": "PRIVATE", "using": 1}]}
    payload = info if where == "resp" else {"body": info if where == "body" else {"data": info}}
    c = client({"ret": "ok", "resp": payload})
    if where == "data":
        assert (await c.maps(ROBOT))[0].active
    else:
        with pytest.raises(CloudError):
            await c.maps(ROBOT)


@pytest.mark.parametrize("error,outcome", [
    (CommandTimeout, "timeout"), (DeviceOffline, "offline"),
    (RateLimited, "busy"), (CannotConnect, "transport"),
])
async def test_error_categories_no_raw_error_or_retry(error, outcome):
    c = client()
    c._device_request.side_effect = error("PRIVATE_TOKEN")
    with pytest.raises(error):
        await c.command(ROBOT, "getMapSet")
    assert c._device_request.await_count == 1


async def test_rejection_retains_only_shape():
    c = client({"ret":"ok", "resp":{"body":{"code":4, "data":{"name":"PRIVATE"}}}})
    with pytest.raises(CommandRejected):
        await c.command(ROBOT, "getMapSubSet")


async def test_budget_cancellation_is_recorded_and_propagated():
    c = client()
    c._device_request.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await c.command(ROBOT, "getCachedMapInfo")


async def test_charge_only_is_valid_optional_position():
    # Reproduces the owner's semantic observation, not a captured response format.
    c = client({"ret":"ok", "resp":{"body":{"data":{"chargePos":[{"x":1,"y":2}]}}}})
    robot, dock = await c.positions(ROBOT)
    assert robot is None and dock is not None
