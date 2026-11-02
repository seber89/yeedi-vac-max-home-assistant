"""Original mixed-account discovery/routing regressions for Issue #3."""
from unittest.mock import AsyncMock

import pytest

from tests.test_client import client
from custom_components.yeedi_vac_max.client import Robot, CloudError


def device(class_id, did='synthetic'):
    return {'class': class_id, 'did': did, 'resource': 'resource', 'nick': 'Vac'}


@pytest.mark.parametrize('class_id', ['04z443', 'mnx7f4'])
@pytest.mark.parametrize('source', [0, 1])
async def test_each_supported_class_from_either_device_list(class_id, source):
    c = client()
    c.authenticate = AsyncMock()
    responses = [{'devices': []}, {'devices': []}]
    responses[source]['devices'] = [device(class_id)]
    c._request = AsyncMock(side_effect=responses)
    robots = await c.devices()
    assert len(robots) == 1 and robots[0].class_id == class_id
    assert c._request.await_count == 2


@pytest.mark.parametrize('items', [[], [device('unsupported')],
    [device(None)], [device(['invalid'])]])
async def test_empty_and_unsupported_lists(items):
    c = client()
    c.authenticate = AsyncMock()
    c._request = AsyncMock(return_value={'devices': items})
    assert await c.devices() == []


async def test_mixed_account_deduplicates_without_losing_class():
    c = client()
    c.authenticate = AsyncMock()
    old, bundle = device('04z443', 'old'), device('mnx7f4', 'bundle')
    c._request = AsyncMock(side_effect=[{'devices': [old, device('other'), bundle]},
                                         {'devices': [bundle, old]}])
    robots = await c.devices()
    assert [(r.did, r.class_id) for r in robots] == [('old', '04z443'), ('bundle', 'mnx7f4')]
    c._request = AsyncMock(return_value={'ret': 'ok', 'resp': {'body': {'code': 0}}})
    for robot in robots:
        await c.command(robot, 'charge', {'act': 'go'}, writing=True)
        request = c._request.call_args.kwargs
        assert request['params']['mid'] == request['json']['toType'] == robot.class_id
        assert request['json']['toId'] == robot.did
        assert request['retry'] is False


@pytest.mark.parametrize('class_id', ['04z443', 'mnx7f4'])
@pytest.mark.parametrize('writing', [False, True])
async def test_command_uses_robot_class_without_changing_profile(class_id, writing):
    c = client()
    c.authenticate = AsyncMock()
    c._request = AsyncMock(return_value={'ret': 'ok', 'resp': {'body': {'code': 0}}})
    robot = Robot('synthetic', 'resource', 'Vac', class_id)
    name, data = ('charge', {'act': 'go'}) if writing else ('getPos', ['chargePos', 'deebotPos'])
    await c.command(robot, name, data, writing=writing)
    request = c._request.call_args.kwargs
    assert request['params']['mid'] == request['json']['toType'] == class_id
    assert request['json']['payload']['body']['data'] == data
    assert request['retry'] is (not writing)


def test_three_argument_robot_keeps_legacy_default():
    assert Robot('synthetic', 'resource', 'Vac').class_id == '04z443'


async def test_conflicting_duplicate_class_is_not_silently_rerouted():
    c = client()
    c.authenticate = AsyncMock()
    c._request = AsyncMock(side_effect=[{'devices': [device('04z443')]},
                                       {'devices': [device('mnx7f4')]}])
    with pytest.raises(CloudError, match='Conflicting device class'):
        await c.devices()


async def test_unsupported_robot_never_sends_a_command():
    c = client()
    c.authenticate = AsyncMock()
    c._request = AsyncMock()
    with pytest.raises(CloudError, match='Unsupported device class'):
        await c.command(Robot('synthetic', 'resource', 'Vac', 'other'), 'charge', writing=True)
    c.authenticate.assert_not_awaited()
    c._request.assert_not_awaited()
