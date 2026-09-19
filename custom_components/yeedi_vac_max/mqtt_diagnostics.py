"""One-shot passive ATR diagnostics. No device publishing, rendering or raw export."""
import asyncio
import base64
import copy
import hashlib
import json
import lzma
import re
import ssl
import struct
import time

from .mqtt_wire import PassiveConnection

from .structure_diagnostics import kind, OUTLINE_FIELDS
from .zero_pixel_diagnostics import bucket

BROKER = 'mq-eu.ecouser.net'
PORT = 443
# Reserve time for disconnect; the observation is never a persistent connection.
WINDOW = 85
IO_TIMEOUT = 2
MAX_MESSAGES = 256
MAX_PAYLOAD = 768 * 1024
NAMES = ('MajorMap', 'MinorMap', 'MapInfo', 'MapSubSet')
ALIASES = {prefix + name: name for prefix in ('', 'on', 'get', 'Get', 'report') for name in NAMES}
FIELDS = {
    'MajorMap': ('mid', 'type', 'pieceWidth', 'pieceHeight', 'cellWidth', 'cellHeight', 'pixel', 'value'),
    'MinorMap': ('mid', 'type', 'pieceIndex', 'pieceValue', 'value'),
    'MapInfo': OUTLINE_FIELDS,
    'MapSubSet': ('mid', 'mssid', 'type', 'value'),
}


def empty_probe():
    flags = ('connection_attempted', 'connected', 'subscribed', 'observation_window_completed',
             'major_map_seen', 'minor_map_seen', 'map_info_seen', 'map_subset_seen',
             'major_crc_list_detected', 'major_crc_all_same', 'minor_all_encoded_identical',
             'mqtt_nonzero_map_data_seen')
    counts = ('major_crc_distinct_count_bucket', 'minor_message_count_bucket',
              'minor_encoded_distinct_count_bucket', 'minor_decode_success_count_bucket',
              'minor_zero_piece_count_bucket', 'minor_nonzero_piece_count_bucket',
              'minor_decoded_distinct_count_bucket')
    return {**dict.fromkeys(flags, False), **dict.fromkeys(counts, '0'), 'message_shapes': {}}


def value_shape(data, name):
    value = data.get(name)
    result = {'present': name in data, 'type': kind(value)}
    if name in ('value', 'pieceValue') and isinstance(value, str):
        result.update(empty=not value, length_bucket=next((label for limit, label in (
            (0, '0'), (64, '1-64'), (256, '65-256'), (1024, '257-1024'),
            (4096, '1025-4096')) if len(value) <= limit), '>4096'))
        if name == 'pieceValue':
            result['base64_charset_only'] = bool(value) and re.fullmatch(r'[A-Za-z0-9+/=]+', value) is not None
    return result


def diagnostic_decode(value):
    """Bounded Legacy-LZMA only; no raster identity/geometry interpretation.

    The already evidenced nine-byte header declares output size. This separate
    diagnostic never relaxes or modifies the functional map decoder.
    """
    if not isinstance(value, str) or not 0 < len(value) <= 512 * 1024:
        raise ValueError('Invalid diagnostic piece')
    packed = base64.b64decode(value, validate=True)
    if len(packed) < 10 or base64.b64encode(packed).decode('ascii') != value:
        raise ValueError('Invalid diagnostic piece')
    size = int.from_bytes(packed[5:9], 'little')
    dictionary = int.from_bytes(packed[1:5], 'little')
    if not 0 < size <= 256 * 256 or not 4096 <= dictionary <= 16 * 1024 * 1024:
        raise ValueError('Invalid diagnostic limits')
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=32 * 1024 * 1024)
    result = decoder.decompress(packed[:5] + struct.pack('<Q', size) + packed[9:], max_length=size + 1)
    if len(result) != size or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid diagnostic size')
    return result


class MapMessages:
    """Bounded transient equality sets; diagnostics contain only derived shapes."""

    def __init__(self):
        self.result = empty_probe()
        self._encoded = set()
        self._decoded = set()
        self._messages = self._minor = self._success = self._zero = 0

    def receive(self, name, payload):
        if name not in NAMES or self._messages >= MAX_MESSAGES:
            return
        if not isinstance(payload, (bytes, bytearray, str)) or len(payload) > MAX_PAYLOAD:
            return
        # Malformed input terminates observation via the listener's neutral catch.
        document = json.loads(payload)
        data = document.get('body', {}).get('data') if isinstance(document, dict) else None
        self._messages += 1
        flag = dict(zip(NAMES, ('major_map_seen', 'minor_map_seen', 'map_info_seen', 'map_subset_seen')))[name]
        self.result[flag] = True
        fields = data if isinstance(data, dict) else {}
        self.result['message_shapes'][name] = {'payload_type': kind(data),
            'fields': {field: value_shape(fields, field) for field in FIELDS[name]}}
        if name == 'MajorMap':
            value = fields.get('value')
            if isinstance(value, str) and 0 < len(value) <= 8192:
                tokens = value.split(',')
                if len(tokens) <= 256 and all(re.fullmatch(r'[0-9]{1,10}', t.strip()) and
                                               int(t) <= 0xffffffff for t in tokens):
                    crcs = {int(t) for t in tokens}
                    self.result.update(major_crc_list_detected=True, major_crc_all_same=len(crcs) == 1,
                        major_crc_distinct_count_bucket=bucket(len(crcs)))
                    self.result['message_shapes'][name]['token_count_bucket'] = bucket(len(tokens))
        if name == 'MinorMap':
            self._minor += 1
            value = fields.get('pieceValue')
            if isinstance(value, str) and len(value) <= 512 * 1024:
                self._encoded.add(hashlib.sha256(value.encode('utf-8')).digest())
                if value:
                    try:
                        pixels = diagnostic_decode(value)
                    except (ValueError, lzma.LZMAError, EOFError):
                        pixels = None  # An undecodable payload is a finding, not a guessed codec.
                    if pixels is not None:
                        self._success += 1
                        self._zero += not any(pixels)
                        self._decoded.add(hashlib.sha256(pixels).digest())
            self.result.update(minor_message_count_bucket=bucket(self._minor),
                minor_encoded_distinct_count_bucket=bucket(len(self._encoded)),
                minor_all_encoded_identical=bool(self._encoded) and len(self._encoded) == 1,
                minor_decode_success_count_bucket=bucket(self._success),
                minor_zero_piece_count_bucket=bucket(self._zero),
                minor_nonzero_piece_count_bucket=bucket(self._success - self._zero),
                minor_decoded_distinct_count_bucket=bucket(len(self._decoded)),
                mqtt_nonzero_map_data_seen=self._success > self._zero)

    def finish(self):
        self._encoded.clear()
        self._decoded.clear()

    def snapshot(self):
        return copy.deepcopy(self.result)


def topic_for(robot):
    # Do not permit wildcard/level injection even from authenticated device data.
    if any(not isinstance(v, str) or not v or len(v) > 256 or
           any(c in v for c in '/+#\x00') for v in (robot.did, robot.resource)):
        raise ValueError('Invalid subscription components')
    return f'iot/atr/+/{robot.did}/04z443/{robot.resource}/j'


def diagnostic_tls():
    """User-authorized exception, passed ONLY to the fixed EU broker below."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


class MqttProbe:
    """One task, one connection attempt, ATR only, no reconnection or publishing."""

    def __init__(self, robots):
        self.probes = {r.did: MapMessages() for r in robots}
        self._robots = tuple(robots)
        self.task = None

    def start(self, hass, entry, client):
        if self.task is None:
            coroutine = self.run(client)
            try:
                self.task = entry.async_create_background_task(hass, coroutine, 'Yeedi temporary MQTT diagnosis')
            except Exception:
                coroutine.close()  # Even scheduling failure must not break setup.

    async def stop(self):
        if self.task is not None:
            if not self.task.cancelling():
                self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    def snapshot(self, robot):
        return self.probes[robot.did].snapshot()

    def _flag(self, name):
        for probe in self.probes.values():
            probe.result[name] = True

    async def run(self, client):
        mqtt = None
        deadline = None
        try:
            if (not all(isinstance(v, str) and v for v in (client.user_id, client.token, client.device_id))
                    or time.monotonic() >= client.expires):
                return  # Never authenticate or invent missing credentials here.
            topics = {topic_for(robot): self.probes[robot.did] for robot in self._robots}
            if not topics:
                return
            mqtt = PassiveConnection(BROKER, PORT, username=client.user_id, password=client.token,
                identifier=f'{client.user_id}@ecouser/{client.device_id}',
                tls_context=diagnostic_tls())
            self._flag('connection_attempted')
            async with asyncio.timeout(WINDOW) as deadline:
                await mqtt.__aenter__()
                self._flag('connected')
                for topic in topics:
                    await mqtt.subscribe(topic, qos=0)
                self._flag('subscribed')
                async for message in mqtt.messages:
                    parts = str(message.topic).split('/')
                    if len(parts) != 7:
                        continue
                    template = '/'.join(parts[:2] + ['+'] + parts[3:])
                    probe = topics.get(template)
                    name = ALIASES.get(parts[2])
                    if probe is not None and name is not None:
                        probe.receive(name, message.payload)
                    await asyncio.sleep(0)  # Let shutdown/deadline run even during bursts.
        except TimeoutError:
            # Only the outer deadline counts as a completed observation window.
            if deadline is not None and deadline.expired() and all(p.result['subscribed'] for p in self.probes.values()):
                self._flag('observation_window_completed')
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # No exception text, logging, re-login, reconnect or HA failure.
        finally:
            if mqtt is not None:
                try:
                    async with asyncio.timeout(IO_TIMEOUT):
                        await mqtt.__aexit__(None, None, None)
                except Exception:
                    pass
            for probe in self.probes.values():
                probe.finish()


def comparison(direct, mqtt):
    return {'direct_https': {
        'pieces_all_identical': direct.get('all_decoded_pieces_identical') is True,
        'decoded_all_zero': direct.get('all_decoded_pieces_zero') is True},
        'mqtt': {'map_messages_seen': any(mqtt[key] for key in
                 ('major_map_seen', 'minor_map_seen', 'map_info_seen', 'map_subset_seen')),
                 'different_piece_payloads_seen': mqtt['minor_encoded_distinct_count_bucket'] not in ('0', '1'),
                 'nonzero_decoded_piece_seen': mqtt['mqtt_nonzero_map_data_seen']}}
