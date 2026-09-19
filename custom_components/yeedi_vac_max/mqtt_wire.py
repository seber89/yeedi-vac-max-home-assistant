"""Original, receive-only MQTT 3.1.1 subset from the OASIS wire specification.

Only CONNECT, one QoS-0 SUBSCRIBE, PINGREQ and DISCONNECT can be emitted.
No publishing API, reconnect, background network thread or persistent session.
"""
import asyncio
from types import SimpleNamespace

MAX_PACKET = 768 * 1024
KEEPALIVE = 30


def text_field(value):
    if not isinstance(value, str) or '\x00' in value:
        raise ValueError('Invalid MQTT string')
    raw = value.encode('utf-8')
    if not 0 < len(raw) <= 65535:
        raise ValueError('Invalid MQTT string')
    return len(raw).to_bytes(2, 'big') + raw


def frame(header, payload=b''):
    if len(payload) > MAX_PACKET:
        raise ValueError('MQTT packet too large')
    remaining = len(payload)
    length = bytearray()
    while True:
        part = remaining % 128
        remaining //= 128
        length.append(part | (128 if remaining else 0))
        if not remaining:
            return bytes([header]) + bytes(length) + payload


async def read_packet(reader):
    header = (await reader.readexactly(1))[0]
    length = 0
    for position in range(4):
        digit = (await reader.readexactly(1))[0]
        length += (digit & 127) * (128 ** position)
        if length > MAX_PACKET:
            raise ValueError('MQTT packet too large')
        if not digit & 128:
            if position and digit == 0:
                raise ValueError('Noncanonical MQTT length')
            return header, await reader.readexactly(length)
    raise ValueError('Invalid MQTT length')


class PassiveConnection:
    """One fixed-broker socket, with bounded, cancellation-safe async cleanup."""

    def __init__(self, hostname, port, *, username, password, identifier, tls_context):
        if hostname != 'mq-eu.ecouser.net' or port != 443:
            raise ValueError('Unsupported diagnostic broker')
        self._credentials = (identifier, username, password)
        self._tls = tls_context
        self._reader = self._writer = None
        self._read_task = None
        self._queued = []

    async def __aenter__(self):
        async with asyncio.timeout(10):
            self._reader, self._writer = await asyncio.open_connection(
                'mq-eu.ecouser.net', 443, ssl=self._tls,
                server_hostname='mq-eu.ecouser.net', ssl_handshake_timeout=5,
                ssl_shutdown_timeout=1, limit=64 * 1024)
            # Protocol name, level 4, username/password + clean session, keepalive.
            body = b'\x00\x04MQTT\x04\xc2' + KEEPALIVE.to_bytes(2, 'big')
            body += b''.join(text_field(value) for value in self._credentials)
            self._credentials = ()
            self._writer.write(frame(0x10, body))
            await self._writer.drain()
            if await read_packet(self._reader) != (0x20, b'\x00\x00'):
                raise ValueError('MQTT connection rejected')
        return self

    async def subscribe(self, topic, qos=0):
        if qos != 0:
            raise ValueError('Diagnostic subscription requires QoS zero')
        async with asyncio.timeout(5):
            self._writer.write(frame(0x82, b'\x00\x01' + text_field(topic) + b'\x00'))
            await self._writer.drain()
            while True:
                header, data = await read_packet(self._reader)
                if header == 0x90:
                    if data != b'\x00\x01\x00':
                        raise ValueError('MQTT subscription rejected')
                    return
                # MQTT permits retained/live publishes before SUBACK.
                if header >> 4 != 3 or len(self._queued) >= 8:
                    raise ValueError('Unexpected MQTT packet')
                self._queued.append(self._message(header, data))

    @staticmethod
    def _message(header, data):
        if header & 6 or len(data) < 2:
            raise ValueError('Unexpected MQTT delivery QoS')
        size = int.from_bytes(data[:2], 'big')
        if not 0 < size <= min(2048, len(data) - 2):
            raise ValueError('Invalid MQTT topic')
        topic = data[2:2+size].decode('utf-8')
        return SimpleNamespace(topic=topic, payload=data[2+size:])

    @property
    def messages(self):
        return self._messages()

    async def _messages(self):
        for message in self._queued:
            yield message
        self._queued.clear()
        ping_pending = False
        loop = asyncio.get_running_loop()
        last_ping = loop.time()
        while True:
            if loop.time() - last_ping >= 10:
                if ping_pending:
                    raise TimeoutError('MQTT keepalive expired')
                self._writer.write(frame(0xc0))
                await self._writer.drain()
                ping_pending = True
                last_ping = loop.time()
            self._read_task = asyncio.create_task(read_packet(self._reader), name='Yeedi MQTT frame')
            while not self._read_task.done():
                done, _ = await asyncio.wait({self._read_task}, timeout=max(0, 10 - (loop.time() - last_ping)))
                if not done:
                    if ping_pending:
                        raise TimeoutError('MQTT keepalive expired')
                    self._writer.write(frame(0xc0))
                    await self._writer.drain()
                    ping_pending = True
                    last_ping = loop.time()
            header, data = self._read_task.result()
            self._read_task = None
            if header == 0xd0 and not data:
                ping_pending = False
            elif header >> 4 == 3:
                yield self._message(header, data)
            else:
                raise ValueError('Unexpected MQTT packet')

    async def __aexit__(self, *args):
        self._credentials = ()
        self._queued.clear()
        writer, self._writer = self._writer, None
        try:
            if self._read_task is not None:
                self._read_task.cancel()
                await asyncio.gather(self._read_task, return_exceptions=True)
                self._read_task = None
            if writer is not None:
                writer.write(frame(0xe0))
                writer.close()
                async with asyncio.timeout(1):
                    await writer.wait_closed()
        finally:
            if writer is not None:
                writer.transport.abort()
            self._reader = None
