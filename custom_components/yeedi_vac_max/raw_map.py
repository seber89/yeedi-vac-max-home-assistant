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
EMPTY_PIECE = 1295764014  # Documented legacy unused-piece sentinel.

MAX_PIXELS = 1024 * 1024
MAX_ENCODED = 512 * 1024


class MapFormatError(ValueError):
    """Generic error: never embed data from the map."""


class MapChanged(MapFormatError):
    """Never retain an old image after observing a changed generation."""


class MapRenderError(MapFormatError):
    """Only fixed stage labels, never payload or an underlying exception text."""

    def __init__(self, stage, assembled=False):
        super().__init__('Map rendering failed')
        self.stage = stage
        self.assembled = assembled


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
                # Keep every nonzero pixel as geometry, including unhandled 5–10.
                raw = piece[x * size + y]
                color = raw if raw <= 3 else 4 if raw == 4 or raw > 10 else 5
                raster[(side - 1 - (tile_y * size + y)) * side + tile_x * size + x] = color
    return bytes(raster)


def render_png(major, pieces):
    """Small original indexed PNG writer; no metadata, IDs or external assets."""
    try:
        raster = assemble(major, pieces)
    except Exception:
        raise MapRenderError('raster_assembly') from None
    if not any(raster):
        raise MapRenderError('no_visible_pixels', True)
    try:
        return _encode_png(raster, major.side)
    except Exception:
        raise MapRenderError('png_generation', True) from None


DISPLAY_TARGET = 320
MAX_DISPLAY_SCALE = 8
MAX_DISPLAY_SIDE = 1040  # Full 1024px input plus bounded display-only padding.


def _display_raster(raster, side):
    """Crop all nonzero geometry, pad and enlarge only the presentation raster.

    Integer nearest-neighbor scaling keeps every original cell/color and aspect
    ratio intact. No downsampling, coordinate inference or changes to map state.
    """
    if (type(side) is not int or side <= 0 or side * side > MAX_PIXELS
            or not isinstance(raster, bytes) or len(raster) != side * side):
        raise MapFormatError('Invalid display raster')
    min_x = min_y = side
    max_x = max_y = -1
    for offset, color in enumerate(raster):
        if color:
            y, x = divmod(offset, side)
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
    if max_x < 0:
        raise MapFormatError('No visible map geometry')
    visible_width, visible_height = max_x - min_x + 1, max_y - min_y + 1
    longest = max(visible_width, visible_height)
    padding = max(1, min(6, math.ceil(longest * .03)))
    width, height = visible_width + 2 * padding, visible_height + 2 * padding
    scale = min(MAX_DISPLAY_SCALE, max(1, math.ceil(DISPLAY_TARGET / longest)),
                MAX_DISPLAY_SIDE // max(width, height))
    if scale < 1:
        raise MapFormatError('Oversized display raster')
    output_width, output_height = width * scale, height * scale
    # Padding is outside the crop even at the original grid edge. It is only
    # background in the presentation and never fed back into the source grid.
    border = bytes(output_width)
    rows = [border] * (padding * scale)
    for y in range(min_y, max_y + 1):
        source = raster[y * side + min_x:y * side + max_x + 1]
        expanded = b''.join(bytes([color]) * scale for color in source)
        row = bytes(padding * scale) + expanded + bytes(padding * scale)
        rows.extend([row] * scale)
    rows.extend([border] * (padding * scale))
    return output_width, output_height, b''.join(rows)


def _encode_png(raster, side):
    width, height, display = _display_raster(raster, side)
    scanlines = b''.join(b'\0' + display[y * width:(y + 1) * width]
                         for y in range(height))

    def chunk(kind, data):
        # PNG container checksum only, NOT an inferred Yeedi piece CRC algorithm.
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 3, 0, 0, 0))
           + chunk(b'PLTE', bytes((239,242,245, 193,212,220, 35,45,55, 161,180,193,
                                  183,199,205, 147,154,161)))
           + chunk(b'IDAT', zlib.compress(scanlines, 6)) + chunk(b'IEND', b''))
    if len(png) > 2 * MAX_PIXELS:
        raise MapFormatError('Oversized image')
    return png


def count_bucket(count):
    return '0' if not count else '1' if count == 1 else '2-8' if count <= 8 else '9-32' if count <= 32 else '33-64' if count <= 64 else '>64'


def safe_status():
    return dict(available=False, complete=False, major_valid=False,
                required_piece_count_bucket='0', loaded_piece_count_bucket='0',
                decoded_piece_count_bucket='0', decode_failures_bucket='0', image_generated=False,
                generation_verified=False, render_attempted=False, raster_assembled=False,
                failure_stage='none')
