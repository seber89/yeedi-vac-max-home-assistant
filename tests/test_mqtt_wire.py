"""Synthetic MQTT framing and async socket teardown, with no external network."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.yeedi_vac_max import mqtt_wire as wire
from custom_components.yeedi_vac_max import mqtt_diagnostics as md
from tests.test_beta63 import ROBOT, session


class Writer:
    def __init__(self, reader, connack=b'\x00\x00', suback=b'\x00\x01\x00'):
        self.reader = reader
        self.connack = connack
        self.suback = suback
        self.sent = []
        self.closed = False
        self.transport = Mock()

    def write(self, value):
        self.sent.append(value)
        if value[0] == 0x10:
            self.reader.feed_data(wire.frame(0x20, self.connack))
        elif value[0] == 0x82:
            self.reader.feed_data(wire.frame(0x90, self.suback))

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


@pytest.fixture
async def socket(monkeypatch):
    reader = asyncio.StreamReader()
    writer = Writer(reader)
    connect = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr(wire.asyncio, 'open_connection', connect)
    return reader, writer, connect


def connection():
    return wire.PassiveConnection(md.BROKER, md.PORT, username='PRIVATE_USER', password='PRIVATE_TOKEN',
                                  identifier='PRIVATE_APP', tls_context=md.diagnostic_tls())


async def test_wire_connect_protocol4_subscribe_disconnect(socket):
    reader, writer, connect = socket
    client = connection()
    await client.__aenter__()
    assert b'\x00\x04MQTT\x04\xc2\x00\x1e' in writer.sent[0]
    assert client._credentials == ()
    await client.subscribe(md.topic_for(ROBOT))
    assert writer.sent[1][0] == 0x82
    assert md.topic_for(ROBOT).encode() in writer.sent[1]
    assert connect.call_args.args == (md.BROKER, 443)
    options = connect.call_args.kwargs
    assert options['server_hostname'] == md.BROKER
    assert options['ssl_handshake_timeout'] == 5
    await client.__aexit__()
    assert writer.closed and writer.sent[-1] == b'\xe0\x00'
    writer.transport.abort.assert_called_once()
    assert client._writer is None and client._reader is None
    assert {packet[0] >> 4 for packet in writer.sent} <= {1, 8, 12, 14}


async def test_passive_publish_classification_and_read_task_cleanup(socket, monkeypatch):
    reader, writer, _ = socket
    monkeypatch.setattr(md, 'WINDOW', .02)
    topic = md.topic_for(ROBOT).replace('+', 'onMapInfo')
    # Pre-SUBACK PUBLISH is legal; inject after the two handshake packets.
    original = writer.write
    def write(packet):
        original(packet)
        if packet[0] == 0x82:
            reader.feed_data(wire.frame(0x30, wire.text_field(topic) + b'{"body":{"data":{}}}'))
    writer.write = write
    before = set(asyncio.all_tasks())
    probe = md.MqttProbe([ROBOT])
    await probe.run(session())
    assert probe.snapshot(ROBOT)['map_info_seen']
    assert writer.closed
    assert not (set(asyncio.all_tasks()) - before)


@pytest.mark.parametrize('phase', ['connect', 'subscribe'])
async def test_rejected_ack_closes_socket(socket, phase):
    _, writer, _ = socket
    if phase == 'connect':
        writer.connack = b'\x00\x05'
    else:
        writer.suback = b'\x00\x01\x80'
    probe = md.MqttProbe([ROBOT])
    await probe.run(session())
    assert writer.closed
    assert not probe.snapshot(ROBOT)['observation_window_completed']


async def test_cancel_during_connection_no_late_socket(monkeypatch):
    started, finished = asyncio.Event(), asyncio.Event()
    async def connect(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()
    monkeypatch.setattr(wire.asyncio, 'open_connection', connect)
    probe = md.MqttProbe([ROBOT])
    probe.task = asyncio.create_task(probe.run(session()))
    await started.wait()
    await probe.stop()
    assert finished.is_set() and probe.task is None


async def test_cancel_waiting_for_connack(socket):
    _, writer, _ = socket
    writer.write = Mock()  # No CONNACK.
    probe = md.MqttProbe([ROBOT])
    probe.task = asyncio.create_task(probe.run(session()))
    await asyncio.sleep(0)
    await probe.stop()
    assert writer.closed


@pytest.mark.parametrize('size', [0, 1, 127, 128, 16383, 16384, wire.MAX_PACKET])
async def test_packet_lengths(size):
    reader = asyncio.StreamReader()
    reader.feed_data(wire.frame(0x30, b'x'*size))
    assert await wire.read_packet(reader) == (0x30, b'x'*size)


@pytest.mark.parametrize('data', [b'\x30\xff\xff\xff\xff', b'\x30\x80\x00'])
async def test_invalid_packet_size(data):
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    with pytest.raises(ValueError):
        await wire.read_packet(reader)


@pytest.mark.parametrize('header,body', [(0x32,b'\x00\x01a'), (0x30,b''), (0x30,b'\x00\x10a')])
def test_malformed_publish(header, body):
    with pytest.raises(ValueError):
        wire.PassiveConnection._message(header, body)


def test_reject_other_broker():
    with pytest.raises(ValueError):
        wire.PassiveConnection('other.example', 443, username='', password='', identifier='', tls_context=None)


async def test_shutdown_transport_aborted_if_wait_closed_fails(socket):
    _, writer, _ = socket
    client = connection()
    await client.__aenter__()
    writer.wait_closed = AsyncMock(side_effect=RuntimeError('synthetic failure'))
    with pytest.raises(RuntimeError):
        await client.__aexit__()
    writer.transport.abort.assert_called_once()
