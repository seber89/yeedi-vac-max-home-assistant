"""Original synthetic broker/lifecycle/privacy tests; never use a real account."""
import asyncio
import json
import ssl
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.yeedi_vac_max import mqtt_diagnostics as md
from custom_components.yeedi_vac_max.client import Robot
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics
from tests.test_beta6 import encoded
from tests.test_coordinator import coordinator

ROBOT = Robot('PRIVATE_DID', 'PRIVATE_RESOURCE', 'PRIVATE_NAME')


def payload(data):
    return json.dumps({'body': {'data': data}}).encode()


def session():
    return SimpleNamespace(user_id='PRIVATE_USER', token='PRIVATE_TOKEN',
                           device_id='PRIVATE_APP', expires=time.monotonic() + 1000)


def message(name='onMinorMap', data=None, robot=ROBOT):
    return SimpleNamespace(topic=md.topic_for(robot).replace('+', name),
                           payload=payload(data or {}))


class FakeBroker:
    def __init__(self, messages=(), connect_error=False, subscribe_error=False):
        self.items = list(messages)
        self.connect_error = connect_error
        self.subscribe_error = subscribe_error
        self.entered = asyncio.Event()
        self.closed = False
        self.subscriptions = []

    async def __aenter__(self):
        self.entered.set()
        if self.connect_error:
            raise RuntimeError('PRIVATE_TOKEN PRIVATE_TOPIC')
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def subscribe(self, topic, qos):
        if self.subscribe_error:
            raise RuntimeError('PRIVATE_TOPIC PRIVATE_TOKEN')
        self.subscriptions.append(topic)

    @property
    def messages(self):
        async def stream():
            for item in self.items:
                yield item
            await asyncio.Event().wait()
        return stream()


@pytest.fixture
def install(monkeypatch):
    monkeypatch.setattr(md, 'WINDOW', .025)
    def factory(broker):
        constructor = Mock(return_value=broker)
        monkeypatch.setattr(md, 'PassiveConnection', constructor)
        return constructor
    return factory


def test_isolated_tls_and_topic():
    normal = ssl.create_default_context()
    custom = md.diagnostic_tls()
    assert custom is not normal
    assert custom.verify_mode == ssl.CERT_NONE and not custom.check_hostname
    assert normal.verify_mode == ssl.CERT_REQUIRED and normal.check_hostname
    assert md.topic_for(ROBOT) == 'iot/atr/+/PRIVATE_DID/04z443/PRIVATE_RESOURCE/j'
    assert md.WINDOW + md.IO_TIMEOUT <= 90


@pytest.mark.parametrize('bad', ['', '#', '+', 'a/b', '\x00', None, 'x'*257])
def test_topic_injection_rejected(bad):
    with pytest.raises(ValueError):
        md.topic_for(Robot(bad, 'resource', 'Name'))


async def test_connect_subscribe_deadline_cleanup(install, caplog):
    broker = FakeBroker([message(data={'pieceValue': encoded(b'\1\0\0\0')})])
    constructor = install(broker)
    probe = md.MqttProbe([ROBOT])
    await probe.run(session())
    args, options = constructor.call_args
    assert args == ('mq-eu.ecouser.net', 443)
    assert options['username'] == 'PRIVATE_USER'
    assert options['password'] == 'PRIVATE_TOKEN'
    assert options['identifier'] == 'PRIVATE_USER@ecouser/PRIVATE_APP'
    assert broker.subscriptions == [md.topic_for(ROBOT)]
    result = probe.snapshot(ROBOT)
    assert all(result[k] for k in ('connection_attempted', 'connected', 'subscribed',
                                  'observation_window_completed', 'mqtt_nonzero_map_data_seen'))
    assert broker.closed
    assert constructor.call_count == 1  # No automatic reconnect.
    assert not probe.probes[ROBOT.did]._encoded and not probe.probes[ROBOT.did]._decoded
    assert 'PRIVATE' not in json.dumps(result) + caplog.text


@pytest.mark.parametrize('stage', ['connect', 'subscribe', 'receive'])
async def test_failure_isolated_no_reconnect(stage, install, caplog):
    broker = FakeBroker(connect_error=stage == 'connect', subscribe_error=stage == 'subscribe')
    if stage == 'receive':
        broker.items = [SimpleNamespace(topic=md.topic_for(ROBOT).replace('+', 'MinorMap'), payload=b'{PRIVATE')]
    constructor = install(broker)
    probe = md.MqttProbe([ROBOT])
    await probe.run(session())
    assert broker.closed and constructor.call_count == 1
    assert not probe.snapshot(ROBOT)['observation_window_completed']
    assert 'PRIVATE' not in json.dumps(probe.snapshot(ROBOT)) + caplog.text


@pytest.mark.parametrize('field,value', [('user_id',''), ('token',''), ('device_id',''), ('expires',0)])
async def test_missing_session_no_login(field, value, install):
    constructor = install(FakeBroker())
    client = session()
    setattr(client, field, value)
    probe = md.MqttProbe([ROBOT])
    await probe.run(client)
    constructor.assert_not_called()
    assert not probe.snapshot(ROBOT)['connection_attempted']


async def test_start_once_and_unload(install):
    broker = FakeBroker()
    constructor = install(broker)
    entry = SimpleNamespace(async_create_background_task=lambda hass, coro, name: asyncio.create_task(coro))
    probe = md.MqttProbe([ROBOT])
    probe.start(None, entry, session())
    task = probe.task
    probe.start(None, entry, session())
    assert task is probe.task
    await broker.entered.wait()
    await probe.stop()
    assert task.done() and broker.closed and probe.task is None
    assert not probe.snapshot(ROBOT)['observation_window_completed']
    assert constructor.call_count == 1


def test_scheduling_failure_isolated():
    probe = md.MqttProbe([ROBOT])
    probe.start(None, SimpleNamespace(async_create_background_task=Mock(side_effect=RuntimeError)), session())
    assert probe.task is None


@pytest.mark.parametrize('name', md.NAMES)
def test_known_names_and_safe_shapes(name):
    probe = md.MapMessages()
    probe.receive(name, payload({'mid':'PRIVATE_MAP', 'mssid':'PRIVATE_ROOM', 'value':'PRIVATE_VALUE',
                                'pieceValue':'', 'width':654321, 'name':'PRIVATE_NAME'}))
    result = probe.snapshot()
    assert result['message_shapes'][name]['payload_type'] == 'object'
    assert 'PRIVATE' not in json.dumps(result) and '654321' not in json.dumps(result)


@pytest.mark.parametrize('crcs,expected,same', [('17,17','1',True), ('17,19','2-8',False),
                                               ('','0',False), ('17,bad','0',False),
                                               ('4294967296','0',False)])
def test_major_crc_classification(crcs, expected, same):
    probe = md.MapMessages()
    probe.receive('MajorMap', payload({'value':crcs}))
    result = probe.snapshot()
    assert result['major_crc_distinct_count_bucket'] == expected
    assert result['major_crc_all_same'] is same


@pytest.mark.parametrize('values,success,zeros,nonzero,distinct', [
    ([''],'0','0','0','0'), (['bad'],'0','0','0','0'),
    ([encoded(b'\0'*4)],'1','1','0','1'),
    ([encoded(b'\1'*4)],'1','0','1','1'),
    ([encoded(b'\0'*4)]*2,'2-8','2-8','0','1'),
    ([encoded(b'\0'*4),encoded(b'\1'*4)],'2-8','1','1','2-8')])
def test_minor_zero_nonzero_uniqueness(values, success, zeros, nonzero, distinct):
    probe = md.MapMessages()
    for value in values:
        probe.receive('MinorMap', payload({'pieceValue':value}))
    result = probe.snapshot()
    assert result['minor_decode_success_count_bucket'] == success
    assert result['minor_zero_piece_count_bucket'] == zeros
    assert result['minor_nonzero_piece_count_bucket'] == nonzero
    assert result['minor_decoded_distinct_count_bucket'] == distinct
    assert result['mqtt_nonzero_map_data_seen'] == (nonzero != '0')
    probe.finish()
    assert not probe._encoded and not probe._decoded


@pytest.mark.parametrize('value', ['', 'not base64', 'A'* (512*1024+1), encoded(b'\0'*65537)],
                         ids=['empty', 'invalid', 'encoded_limit', 'decoded_limit'])
def test_decode_limits(value):
    with pytest.raises((ValueError, md.lzma.LZMAError)):
        md.diagnostic_decode(value)


def test_message_bounds_and_unknown():
    p = md.MapMessages()
    p.receive('unknown', b'bad')
    p.receive('MinorMap', b'x' * (md.MAX_PAYLOAD+1))
    assert p._messages == 0
    for _ in range(md.MAX_MESSAGES + 5):
        p.receive('MinorMap', payload({'pieceValue':''}))
    assert p._messages == md.MAX_MESSAGES


async def test_wrong_robot_topic_ignored(install):
    broker = FakeBroker([message(robot=Robot('OTHER', 'resource', 'Name'))])
    install(broker)
    p = md.MqttProbe([ROBOT])
    await p.run(session())
    assert not p.snapshot(ROBOT)['minor_map_seen']


async def test_diagnostics_and_coordinator_survive_failure(coordinator, install, caplog):
    install(FakeBroker(connect_error=True))
    p = md.MqttProbe(coordinator.robots)
    coordinator.mqtt_probe = p
    await p.run(session())
    assert (await coordinator._async_update_data())['vac']['online']
    result = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=coordinator))
    assert 'mqtt_live_map_probe' in result and 'map_transport_comparison' in result
    assert 'PRIVATE' not in json.dumps(result) + caplog.text


def test_comparison_only_facts():
    mqtt = md.empty_probe()
    result = md.comparison({'all_decoded_pieces_identical':True, 'all_decoded_pieces_zero':True}, mqtt)
    assert all(result['direct_https'].values())
    assert not any(result['mqtt'].values())


def test_no_publish_or_functional_map_use():
    import ast
    from pathlib import Path
    tree = ast.parse(Path(md.__file__).read_text())
    calls = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert not {'publish', 'authenticate', 'command', 'render_png', 'assemble'}.intersection(calls)


async def test_real_ha_shutdown_cancels_entry_task(coordinator, install):
    from homeassistant.core import CoreState
    broker = FakeBroker()
    install(broker)
    probe = md.MqttProbe(coordinator.robots)
    probe.start(coordinator.hass, coordinator.config_entry, session())
    task = probe.task
    await broker.entered.wait()
    coordinator.hass.state = CoreState.running
    await coordinator.hass.async_stop()
    assert task.done() and broker.closed


@pytest.mark.parametrize('alias', tuple(md.ALIASES))
async def test_known_aliases_only(alias, install):
    broker = FakeBroker([message(alias)])
    install(broker)
    probe = md.MqttProbe([ROBOT])
    await probe.run(session())
    assert set(probe.snapshot(ROBOT)['message_shapes']) == {md.ALIASES[alias]}


def test_valid_payload_never_in_export():
    value = encoded(bytes(range(128)))
    probe = md.MapMessages()
    probe.receive('MinorMap', payload({'pieceValue':value, 'mid':'PRIVATE_MAP', 'pieceIndex':135791}))
    result = json.dumps(probe.snapshot())
    assert value not in result and 'PRIVATE_MAP' not in result and '135791' not in result
