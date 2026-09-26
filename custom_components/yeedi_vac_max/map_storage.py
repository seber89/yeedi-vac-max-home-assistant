"""Private, versioned last-good PNG storage. Never store live map/position data."""
import asyncio
import base64
import binascii
from dataclasses import dataclass
import struct
import zlib

from homeassistant.helpers.storage import Store

from .map_data import identifier

MAX_PNG = 2 * 1024 * 1024


@dataclass(frozen=True, repr=False)
class SavedMap:
    map_id: str
    png: bytes


def valid_png(png):
    """Bounded structural validation of our indexed PNG, without rendering it."""
    if not isinstance(png, bytes) or not 57 <= len(png) <= MAX_PNG:
        return False
    if png[:8] != b'\x89PNG\r\n\x1a\n':
        return False
    offset, kinds = 8, []
    while offset + 12 <= len(png):
        size = int.from_bytes(png[offset:offset+4], 'big')
        end = offset + 12 + size
        if end > len(png):
            return False
        kind = png[offset+4:offset+8]
        data = png[offset+8:end-4]
        if zlib.crc32(kind + data) & 0xffffffff != int.from_bytes(png[end-4:end], 'big'):
            return False
        if kind == b'IHDR':
            if kinds or len(data) != 13:
                return False
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            if not (0 < width <= 1040 and 0 < height <= 1040
                    and (depth, color, compression, filtering, interlace) == (8, 3, 0, 0, 0)):
                return False
        if kind not in (b'IHDR', b'PLTE', b'tRNS', b'IDAT', b'IEND'):
            return False
        kinds.append(kind)
        offset = end
        if kind == b'IEND':
            return size == 0 and offset == len(png) and kinds == [b'IHDR', b'PLTE', b'IDAT', b'IEND']
    return False


class MapStorage:
    """One entry-scoped private store; exact device identity, never name matching."""
    def __init__(self, hass, entry_id):
        self.store = Store(hass, 1, f'yeedi_vac_max.map.{entry_id}',
                           private=True, atomic_writes=True)
        self.records = {}
        self.lock = asyncio.Lock()

    async def load(self, robot_ids):
        try:
            data = await self.store.async_load()
            if not isinstance(data, dict):
                return {}
            loaded = {}
            for did, record in data.items():
                if not isinstance(did, str):
                    continue
                if not isinstance(record, dict) or set(record) != {'map_id', 'png'}:
                    continue
                mid, encoded = record['map_id'], record['png']
                if not isinstance(mid, str) or identifier(mid) != mid or mid == '0':
                    continue
                if not isinstance(encoded, str) or len(encoded) > (MAX_PNG + 2) // 3 * 4:
                    continue
                try:
                    png = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error):
                    continue
                if valid_png(png):
                    if did in robot_ids:
                        loaded[did] = SavedMap(mid, png)
                    self.records[did] = record
            return loaded
        except Exception:
            return {}  # Optional private cache: no exception text or payload logging.

    async def save(self, did, saved):
        if not valid_png(saved.png) or identifier(saved.map_id) != saved.map_id or saved.map_id == '0':
            return False
        return await self._write(did, {'map_id': saved.map_id,
                                      'png': base64.b64encode(saved.png).decode('ascii')})

    async def discard(self, did):
        return await self._write(did, None)

    async def _write(self, did, record):
        async with self.lock:
            updated = dict(self.records)
            if record is None:
                updated.pop(did, None)
            else:
                updated[did] = record
            if updated == self.records:
                return True
            try:
                await self.store.async_save(updated)
                # Store may report filesystem failures via HA's logger rather
                # than raising. Confirm the atomic write through its public API.
                if await self.store.async_load() != updated:
                    return False
            except Exception:
                return False
            self.records = updated
            return True
