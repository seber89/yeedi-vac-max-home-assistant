"""Synthetic privacy probes, NOT evidence of a real map response."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.yeedi_vac_max.client import (
    YeediClient, Robot, CloudError, CommandRejected, CommandTimeout,
    DeviceOffline, RateLimited, CannotConnect,
)
from custom_components.yeedi_vac_max.structure_diagnostics import response_structure, shape
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
    probe = output["structure_probe"][0]["getCachedMapInfo"]
    assert probe["command_success"] is True
    level = probe["levels"]["resp.body.data"]
    assert level["info_count"] == 1
    assert level["active_candidate_count"] == 1
    assert level["info_using_types"] == ["number"]
    assert level["subsets_mssid_types"] == ["string"]
    assert level["chargePos_type"] == "array"
    assert output["structure_probe"][0]["getMapSet"] == {"attempted": False}
    probe["outcome"] = "modified"
    assert c.structure_diagnostics(ROBOT)["getCachedMapInfo"]["outcome"] == "accepted_read"
    c.close()
    assert c.structure_diagnostics(ROBOT)["getCachedMapInfo"] == {"attempted": False}


@pytest.mark.parametrize("using,expected", [(1,1), ("1",1), (True,0), (0,0), ("true",0), ({"PRIVATE":1},0)])
def test_using_types_only_not_guessing(using, expected):
    result = shape({"info": [{"mid": "PRIVATE", "using": using}]})
    assert result["active_candidate_count"] == expected
    assert "PRIVATE" not in json.dumps(result)


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
    path = {"resp": "resp", "body": "resp.body", "data": "resp.body.data"}[where]
    assert c.structure_diagnostics(ROBOT)["getCachedMapInfo"]["levels"][path]["info_present"]


@pytest.mark.parametrize("error,outcome", [
    (CommandTimeout, "timeout"), (DeviceOffline, "offline"),
    (RateLimited, "busy"), (CannotConnect, "transport"),
])
async def test_error_categories_no_raw_error_or_retry(error, outcome):
    c = client()
    c._device_request.side_effect = error("PRIVATE_TOKEN")
    with pytest.raises(error):
        await c.command(ROBOT, "getMapSet")
    probe = c.structure_diagnostics(ROBOT)["getMapSet"]
    assert probe["outcome"] == outcome
    assert not probe["command_success"] and not probe["response_received"]
    assert "PRIVATE" not in json.dumps(probe)
    assert c._device_request.await_count == 1


async def test_rejection_retains_only_shape():
    c = client({"ret":"ok", "resp":{"body":{"code":4, "data":{"name":"PRIVATE"}}}})
    with pytest.raises(CommandRejected):
        await c.command(ROBOT, "getMapSubSet")
    probe = c.structure_diagnostics(ROBOT)["getMapSubSet"]
    assert probe["outcome"] == "rejected" and probe["response_received"]
    assert "PRIVATE" not in json.dumps(probe)


async def test_budget_cancellation_is_recorded_and_propagated():
    c = client()
    c._device_request.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await c.command(ROBOT, "getCachedMapInfo")
    assert c.structure_diagnostics(ROBOT)["getCachedMapInfo"]["outcome"] == "cancelled_or_budget_expired"


async def test_charge_only_is_valid_optional_position():
    # Reproduces the owner's semantic observation, not a captured response format.
    c = client({"ret":"ok", "resp":{"body":{"data":{"chargePos":[{"x":1,"y":2}]}}}})
    robot, dock = await c.positions(ROBOT)
    assert robot is None and dock is not None
    level = c.structure_diagnostics(ROBOT)["getPos"]["levels"]["resp.body.data"]
    assert not level["deebotPos_present"] and level["chargePos_present"]


def test_large_and_malformed_shapes_are_bounded():
    result = shape({"info": [{"mid":"PRIVATE", "using":1}] * 101})
    assert result["info_count"] == 101
    assert result["info_inspection_truncated"]
    assert result["active_candidate_count"] == 100
    assert response_structure({"resp":"PRIVATE_INVALID_JSON"})["levels"]["resp"]["type"] == "null"


async def test_non_spatial_and_write_commands_not_probed():
    c = client({"ret":"ok", "resp":{"body":{"code":0}}})
    await c.command(ROBOT, "clean", {"act":"start"}, writing=True)
    await c.command(ROBOT, "getBattery")
    assert all(not p["attempted"] for p in c.structure_diagnostics(ROBOT).values())
