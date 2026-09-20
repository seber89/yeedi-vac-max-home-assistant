"""Release cleanup contracts, with synthetic data only."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from tests.test_beta6 import client, ROBOT, MID
from custom_components.yeedi_vac_max import client as cloud
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics
from custom_components.yeedi_vac_max.raw_map import safe_status

COMPONENT = Path(cloud.__file__).parent
REMOVED = ("mqtt_diagnostics", "mqtt_wire", "structure_diagnostics",
           "geometry_diagnostics", "transport_diagnostics", "zero_pixel_diagnostics")


@pytest.mark.parametrize("name", REMOVED)
def test_no_research_module_or_runtime_import(name):
    assert not (COMPONENT / (name + ".py")).exists()
    for path in COMPONENT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != name
            if isinstance(node, ast.Import):
                assert name not in [alias.name for alias in node.names]


def test_no_mqtt_transport_or_unsafe_tls_configuration():
    source = "\n".join(p.read_text(encoding="utf-8") for p in COMPONENT.glob("*.py"))
    for forbidden in ("CERT_NONE", "check_hostname", "rejectUnauthorized",
                      "mq-eu.ecouser.net", "MqttProbe", "mqtt_probe",
                      "asyncio.open_connection", "ssl=False", "verify_ssl=False"):
        assert forbidden not in source
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["requirements"] == []
    assert manifest["version"] == "0.2.0-rc.3"


@pytest.mark.parametrize("private", ["PRIVATE_ID_TOKEN_TOPIC_CRC", {"PRIVATE": "COORDINATES"}, ["PRIVATE"], 987654321])
async def test_compact_allowlisted_diagnostics(coordinator, caplog, private):
    state = coordinator.spatial["vac"]
    state.raw_status = {key: private for key in safe_status()}
    state.raw_status.update(raw_payload=private, zero_pixel_probe=private)
    output = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=coordinator))
    assert set(output) == {"integration_version", "last_update_success", "robots", "raw_map"}
    raw = output["raw_map"][0]
    assert set(raw) == {"available", "complete", "major_valid", "image_generated",
                       "generation_verified", "failure_stage", "loaded_piece_count_bucket",
                       "decoded_piece_count_bucket", "decode_failures_bucket"}
    assert raw["failure_stage"] == "unexpected"
    assert raw["loaded_piece_count_bucket"] == "0"
    assert not raw["major_valid"]
    assert all(type(value) is bool for value in output["robots"][0].values())
    exported = json.dumps(output) + caplog.text
    assert "PRIVATE" not in exported and "987654321" not in exported


async def test_only_primary_decoder_and_functional_reads(monkeypatch):
    c = client()
    original = cloud.decode_piece
    seen = []
    def decode(*args):
        seen.append(args[2])
        return original(*args)
    monkeypatch.setattr(cloud, "decode_piece", decode)
    status = safe_status()
    result = await c.load_raw_map(ROBOT, MID, None, status)
    assert result and status["generation_verified"]
    assert len(seen) == len(result.major.required)
    assert [call.args[1] for call in c.command.call_args_list].count("getMajorMap") == 2
    assert [call.args[1] for call in c.command.call_args_list].count("getMinorMap") == len(seen)
    assert "zero_pixel_probe" not in status
    assert not any(name in vars(c) for name in ("_structure", "_geometry", "_transport"))


@pytest.mark.parametrize("name", ["getMajorMap", "getMinorMap", "getMapState"])
async def test_read_only_safety_survives_cleanup(name):
    c = cloud.YeediClient(None, "a", "b", "DE", "c")
    c.authenticate = AsyncMock()
    with pytest.raises(ValueError):
        await c.command(ROBOT, name, writing=True)
    c.authenticate.assert_not_awaited()
