"""Original bounded Legacy-LZMA raster implementation; protocol facts in PROTOCOL.md.

No foreign decoder/renderer code. Private state stays in memory and has no repr.
Only the evidenced square, column-major legacy layout is supported.
"""
import base64
import binascii
from dataclasses import dataclass
import lzma
import math
import re
import struct
import zlib

from .map_data import identifier
from .transport_diagnostics import EMPTY_PIECE

MAX_PIXELS = 1024 * 1024
MAX_ENCODED = 512 * 1024


class MapFormatError(ValueError):
    """Generic error: never embed data from the map."""


class MapChanged(MapFormatError):
    """Never retain an old image after observing a changed generation."""


@dataclass(frozen=True, repr=False)
class Major:
    map_id: str
    piece_size: int
    cells: int
    pixel: float
    crcs: tuple[int, ...]

    @property
    def required(self):
        return tuple(i for i, crc in enumerate(self.crcs) if crc != EMPTY_PIECE)

    @property
    def side(self):
        return self.piece_size * self.cells


@dataclass(frozen=True, repr=False)
class RawMap:
    major: Major
    pieces: tuple[bytes | None, ...]
    png: bytes


def parse_major(data, map_id):
    if (not isinstance(map_id, str) or identifier(map_id) != map_id or map_id == '0'
            or not isinstance(data, dict) or data.get('mid') != map_id):
        raise MapFormatError('Invalid map metadata')
    dimensions = []
    for name, maximum in (('pieceWidth',256), ('pieceHeight',256),
                          ('cellWidth',16), ('cellHeight',16)):
        value = data.get(name)
        if type(value) not in (int, float) or not 1 <= value <= maximum or int(value) != value:
            raise MapFormatError('Invalid map dimensions')
        dimensions.append(int(value))
    pw, ph, cw, ch = dimensions
    # Public legacy sources only unambiguously establish the square layout.
    if pw != ph or cw != ch or (pw * cw) ** 2 > MAX_PIXELS:
        raise MapFormatError('Unsupported map dimensions')
    pixel = data.get('pixel')
    if type(pixel) not in (int, float) or not 0 < pixel <= 1000 or not math.isfinite(pixel):
        raise MapFormatError('Invalid map scale')
    value = data.get('value')
    if not isinstance(value, str) or len(value) > 8192:
        raise MapFormatError('Invalid piece list')
    tokens = value.split(',')
    if len(tokens) != cw * ch:
        raise MapFormatError('Invalid piece count')
    crcs = []
    for token in tokens:
        token = token.strip()
        if not re.fullmatch(r'[0-9]{1,10}', token) or int(token) > 0xffffffff:
            raise MapFormatError('Invalid piece list')
        crcs.append(int(token))
    return Major(map_id, pw, cw, float(pixel), tuple(crcs))


def decode_piece(data, major, index):
    if isinstance(data, dict) and isinstance(data.get('mid'), str) and data['mid'] != major.map_id:
        raise MapChanged('Current map changed')
    if (type(index) is not int or index not in major.required or not isinstance(data, dict)
            or data.get('mid') != major.map_id or data.get('type') != 'ol'
            or type(data.get('pieceIndex')) is not int or data['pieceIndex'] != index):
        raise MapFormatError('Piece identity mismatch')
    value = data.get('pieceValue')
    if not isinstance(value, str) or not 0 < len(value) <= MAX_ENCODED:
        raise MapFormatError('Invalid encoded piece')
    try:
        packed = base64.b64decode(value, validate=True)
        if base64.b64encode(packed).decode('ascii') != value or len(packed) < 10:
            raise MapFormatError('Invalid encoded piece')
        # Wire header: properties(1), dictionary-size LE(4), output-size LE(4).
        # Reconstruct the standard LZMA-alone 64-bit output-size header.
        expected = major.piece_size ** 2
        if int.from_bytes(packed[5:9], 'little') != expected:
            raise MapFormatError('Invalid piece size')
        dictionary = int.from_bytes(packed[1:5], 'little')
        if not 4096 <= dictionary <= 16 * 1024 * 1024:
            raise MapFormatError('Invalid compression dictionary')
        stream = packed[:5] + struct.pack('<Q', expected) + packed[9:]
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=32 * 1024 * 1024)
        pixels = decoder.decompress(stream, max_length=expected + 1)
        if len(pixels) != expected or not decoder.eof or decoder.unused_data:
            raise MapFormatError('Incomplete or oversized piece')
        return pixels
    except (binascii.Error, UnicodeError, lzma.LZMAError, EOFError, ValueError):
        raise MapFormatError('Invalid legacy map piece') from None


def assemble(major, pieces):
    """All-or-nothing column-major tiles -> top-down, row-major PNG raster."""
    if len(pieces) != len(major.crcs):
        raise MapFormatError('Incomplete map')
    side, size = major.side, major.piece_size
    raster = bytearray(side * side)
    for index in major.required:
        piece = pieces[index]
        if not isinstance(piece, bytes) or len(piece) != size * size:
            raise MapFormatError('Incomplete map')
        tile_x, tile_y = divmod(index, major.cells)
        for x in range(size):
            for y in range(size):
                # Palette facts: 0 unknown, 1 floor, 2 wall, 3 carpet.
                raw = piece[x * size + y]
                color = raw if raw in (1, 2, 3) else 0
                raster[(side - 1 - (tile_y * size + y)) * side + tile_x * size + x] = color
    return bytes(raster)


def render_png(major, pieces):
    """Small original indexed PNG writer; no metadata, IDs or external assets."""
    raster = assemble(major, pieces)
    side = major.side
    # Crop empty borders for a useful dashboard image, preserving actual pixels.
    min_x = min_y = side
    max_x = max_y = -1
    for offset, color in enumerate(raster):
        if color:
            y, x = divmod(offset, side)
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
    if max_x < 0:
        raise MapFormatError('No visible map geometry')
    left, right = max(0, min_x - 4), min(side, max_x + 5)
    top, bottom = max(0, min_y - 4), min(side, max_y + 5)
    scanlines = b''.join(b'\0' + raster[y * side + left:y * side + right]
                         for y in range(top, bottom))

    def chunk(kind, data):
        # PNG container checksum only, NOT an inferred Yeedi piece CRC algorithm.
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', right-left, bottom-top, 8, 3, 0, 0, 0))
           + chunk(b'PLTE', bytes((239,242,245, 193,212,220, 35,45,55, 161,180,193)))
           + chunk(b'IDAT', zlib.compress(scanlines, 6)) + chunk(b'IEND', b''))
    if len(png) > 2 * MAX_PIXELS:
        raise MapFormatError('Oversized image')
    return png


def count_bucket(count):
    return '0' if not count else '1' if count == 1 else '2-8' if count <= 8 else '9-32' if count <= 32 else '33-64' if count <= 64 else '>64'


def safe_status():
    return dict(available=False, complete=False, major_valid=False,
                required_piece_count_bucket='0', loaded_piece_count_bucket='0',
                decoded_piece_count_bucket='0', decode_failures_bucket='0', image_generated=False)
