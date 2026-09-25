"""Synthetic protocol tests; fixtures are not captured live device responses."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from custom_components.yeedi_vac_max.client import (
    YeediClient, Robot, activity, command_body, signed, md5,
    CloudError, InvalidAuth, VerificationRequired, DeviceOffline, CommandRejected,
    CannotConnect, FAN_SPEEDS,
)

ROBOT = Robot("test-device", "test-resource", "Test vacuum")


def client():
    return YeediClient(None, "test@example.invalid", "test-password", "DE", "test-client")


def test_signature_is_sorted_and_does_not_mutate():
    params = {"b": 2, "a": 1}
    result = signed(params, {"c": 3}, "key", "secret")
    assert result["authSign"] == md5("keya=1b=2c=3secret")
    assert params == {"b": 2, "a": 1}


@pytest.mark.parametrize("clean,charge,expected", [
    ({"state": "idle"}, {"isCharging": 1}, "docked"),
    ({"state": "clean", "cleanState": {"motionState": "working"}}, {}, "cleaning"),
    ({"state": "clean", "cleanState": {"motionState": "pause"}}, {}, "paused"),
    ({"state": "goCharging"}, {}, "returning"),
    ({"state": "idle"}, {}, "idle"),
    ({"trigger": "alert"}, {"isCharging": 1}, "docked"),
    ({"state": "future-value"}, {}, None),
])
def test_states(clean, charge, expected):
    assert activity(clean, charge) == expected


@pytest.mark.parametrize("response,error", [
    ({"ret": "fail", "errno": 4200}, DeviceOffline),
    ({"ret": "fail", "errno": 500}, DeviceOffline),
    ({"ret": "ok", "resp": {"body": {"code": 20003}}}, CommandRejected),
    ({"ret": "ok", "resp": {"body": {"data": {}}}}, CloudError),
    ({"ret": "ok"}, CloudError),
    ({"ret": "ok", "resp": "bad"}, CloudError),
])
def test_writes_require_acknowledgement(response, error):
    with pytest.raises(error):
        command_body(response, writing=True)


def test_encoded_payload():
    assert command_body({"ret": "ok", "resp": json.dumps({"body": {"code": 0}})}, writing=True) == {"code": 0}


async def test_login_direct_yeedi_and_token_cache():
    c = client()
    c._request = AsyncMock(side_effect=[
        {"code": "0000", "data": {"uid": "user", "accessToken": "access"}},
        {"code": "0000", "data": {"authCode": "auth-code"}},
        {"result": "ok", "userId": "short-user", "token": "token", "last": 3600000},
    ])
    await asyncio.gather(c.authenticate(), c.authenticate())
    assert c._request.await_count == 3
    calls = c._request.call_args_list
    assert calls[0].args[1].startswith("https://gl-de-api.yeedi.com/")
    assert calls[0].kwargs["params"]["password"] == md5("test-password")
    assert calls[1].args[1].startswith("https://gl-de-openapi.yeedi.com/")
    assert calls[2].kwargs["json"]["org"] == "ECOYDWW"
    assert c.user_id == "short-user"
    c.close()
    assert not c.token and not c.password


@pytest.mark.parametrize("code,error", [("1005", InvalidAuth), ("1010", InvalidAuth), ("1013", VerificationRequired), ("secret-text", CloudError)])
def test_auth_errors_are_sanitized(code, error):
    with pytest.raises(error) as exc:
        YeediClient._auth_data({"code": code, "msg": "secret-password"})
    assert "secret" not in str(exc.value)


async def test_device_filter_and_deduplication():
    c = client()
    c.authenticate = AsyncMock()
    device = {"class": "04z443", "did": "vac", "resource": "res", "nick": "Vac Max"}
    c._request = AsyncMock(side_effect=[
        {"devices": [device, {"class": "other"}]}, {"devices": [device]}])
    assert await c.devices() == [Robot("vac", "res", "Vac Max")]


async def test_missing_device_list_is_not_no_devices():
    c = client()
    c.authenticate = AsyncMock()
    c._request = AsyncMock(return_value={"result": "fail"})
    with pytest.raises(CloudError):
        await c.devices()


async def test_command_envelope_and_no_write_retry():
    c = client()
    c.authenticate = AsyncMock()
    c.token = "test-token"
    c._request = AsyncMock(return_value={"ret": "ok", "resp": {"body": {"code": 0}}})
    await c.command(ROBOT, "charge", {"act": "go"}, writing=True)
    kwargs = c._request.call_args.kwargs
    assert kwargs["retry"] is False
    assert kwargs["json"]["toType"] == "04z443"
    assert kwargs["json"]["toRes"] == "test-resource"
    assert kwargs["json"]["payload"]["body"]["data"] == {"act": "go"}
    assert kwargs["json"]["auth"]["with"] == "users"


async def test_snapshot_and_model_fan_speeds():
    c = client()
    c.command = AsyncMock(side_effect=[
        {"data": {"value": 72}}, {"data": {"state": "idle"}},
        {"data": {"isCharging": 1}}, {"data": {"speed": 1000}},
    ])
    assert await c.snapshot(ROBOT) == {"online": True, "battery": 72, "activity": "docked", "fan_speed": "Quiet"}
    assert FAN_SPEEDS == {"Quiet": 1000, "Normal": 0, "Max": 1}


async def test_cloud_error_is_distinct_from_offline():
    c = client()
    c.command = AsyncMock(side_effect=CannotConnect("Cannot reach cloud"))
    with pytest.raises(CannotConnect):
        await c.snapshot(ROBOT)
    c.command = AsyncMock(side_effect=DeviceOffline("offline"))
    assert (await c.snapshot(ROBOT))["online"] is False


class Reply:
    status = 200
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def json(self, **kwargs):
        return {"ok": True}


class Session:
    def __init__(self, failures):
        self.failures = failures
        self.calls = 0
    def request(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("password-must-not-leak")
        assert kwargs["allow_redirects"] is False
        assert kwargs["timeout"].total == 15
        return Reply()


async def test_transport_retry_only_when_allowed():
    c = client()
    c.session = Session(1)
    assert await c._request("POST", "https://example.invalid", retry=True) == {"ok": True}
    assert c.session.calls == 2
    c.session = Session(1)
    with pytest.raises(CannotConnect) as exc:
        await c._request("POST", "https://example.invalid")
    assert c.session.calls == 1
    assert "password" not in str(exc.value)
