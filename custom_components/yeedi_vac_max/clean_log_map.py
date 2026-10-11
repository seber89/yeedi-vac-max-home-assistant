"""Bounded historical HTTPS PNG fallback, independently implemented.

Only fixed flags escape this module. URLs and image bytes are private RAM data.
This is not RawMap geometry and must never enter the last-good RawMap store.
"""
import asyncio
from dataclasses import dataclass
import struct
from urllib.parse import urlsplit
import zlib

import aiohttp

MAX_BYTES = 5 * 1024 * 1024
MAX_RECORDS = 100
DOWNLOAD_TIMEOUT = 15
FLAGS = (
    'clean_log_map_attempted', 'clean_log_response_valid',
    'clean_log_records_present', 'clean_log_image_url_present',
    'clean_log_image_url_supported', 'clean_log_image_download_attempted',
    'clean_log_image_downloaded', 'clean_log_png_valid', 'clean_log_fallback_active',
)
ERRORS = frozenset(('none', 'portal_timeout', 'portal_rejected', 'invalid_response',
    'no_records', 'no_image_url', 'unsupported_image_url', 'download_timeout',
    'download_rejected', 'not_png', 'invalid_png', 'too_large', 'map_changed', 'unexpected'))


class CleanLogError(ValueError):
    """Only a fixed category, never input or third-party exception text."""
    def __init__(self, category):
        self.category = category if category in ERRORS else 'unexpected'
        super().__init__(self.category)


@dataclass(frozen=True, repr=False)
class HistoricalMap:
    map_id: str
    png: bytes


def safe_probe(source=None):
    source = source or {}
    result = {key: source.get(key) is True for key in FLAGS}
    error = source.get('error', 'none')
    result['error'] = error if type(error) is str and error in ERRORS else 'unexpected'
    return result


def latest_image_url(response, probe):
    if not isinstance(response, dict):
        raise CleanLogError('invalid_response')
    if response.get('ret') != 'ok':
        raise CleanLogError('portal_rejected')
    logs = response.get('logs')
    if not isinstance(logs, list) or len(logs) > MAX_RECORDS:
        raise CleanLogError('invalid_response')
    probe['clean_log_response_valid'] = True
    probe['clean_log_records_present'] = bool(logs)
    if not logs:
        raise CleanLogError('no_records')
    selected = None
    newest = -1
    for record in logs:
        if not isinstance(record, dict):
            continue
        timestamp, url = record.get('ts'), record.get('imageUrl')
        # Protocol ts is an integer. Reject bools, guessed units and string dates.
        if (type(timestamp) is int and 0 < timestamp < 2**63
                and isinstance(url, str) and url.strip() and timestamp > newest):
            newest, selected = timestamp, url
    if selected is None:
        raise CleanLogError('no_image_url')
    probe['clean_log_image_url_present'] = True
    return selected


def supported_url(url):
    if (not isinstance(url, str) or len(url) > 4096 or not url.startswith('https://')
            or any(ord(c) <= 32 or ord(c) >= 127 for c in url) or '\\' in url or '#' in url):
        return False
    try:
        parsed = urlsplit(url)
        # Exact authority, not a suffix comparison; reject escaped/path traversal too.
        return (parsed.scheme == 'https'
                and parsed.netloc in ('portal-eu.ecouser.net', 'portal-eu.ecouser.net:443')
                and parsed.hostname == 'portal-eu.ecouser.net' and parsed.port in (None, 443)
                and parsed.username is None and parsed.password is None
                and not parsed.fragment and not parsed.query and parsed.path.startswith('/api/lg/image/')
                and '%' not in parsed.path and not any(p in ('.', '..') for p in parsed.path.split('/')))
    except (ValueError, TypeError):
        return False


def validate_png(blob):
    """Validate external PNG framing/CRC, not pixel content or map semantics."""
    if not isinstance(blob, bytes) or not blob.startswith(b'\x89PNG\r\n\x1a\n'):
        raise CleanLogError('not_png')
    if len(blob) > MAX_BYTES:
        raise CleanLogError('too_large')
    offset, chunks, color, idat_bytes = 8, 0, None, 0
    idat = palette = ended_idat = False
    while offset + 12 <= len(blob) and chunks < 4096:
        length = int.from_bytes(blob[offset:offset+4], 'big')
        end = offset + 12 + length
        if end > len(blob):
            break
        kind = blob[offset+4:offset+8]
        data = blob[offset+8:end-4]
        if (not all(65 <= b <= 90 or 97 <= b <= 122 for b in kind)
                or kind[2] & 32
                or zlib.crc32(kind + data) != int.from_bytes(blob[end-4:end], 'big')):
            break
        if chunks == 0:
            if kind != b'IHDR' or length != 13:
                break
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            depths = {0: (1,2,4,8,16), 2: (8,16), 3: (1,2,4,8), 4: (8,16), 6: (8,16)}
            if (not 0 < width <= 4096 or not 0 < height <= 4096
                    or depth not in depths.get(color, ()) or compression != 0
                    or filtering != 0 or interlace not in (0,1)):
                break
        elif kind == b'IHDR':
            break
        elif kind == b'PLTE':
            if palette or idat or color in (0,4) or not 0 < length <= 768 or length % 3:
                break
            if color == 3 and length // 3 > 2**depth:
                break
            palette = True
        elif kind == b'IDAT':
            if ended_idat or (color == 3 and not palette):
                break
            idat = True
            idat_bytes += length
        elif kind == b'IEND':
            if length == 0 and idat_bytes > 0 and end == len(blob):
                return
            break
        elif not kind[0] & 32:  # Unknown critical chunk, including unsupported formats.
            break
        if idat and kind != b'IDAT':
            ended_idat = True
        offset, chunks = end, chunks + 1
    raise CleanLogError('invalid_png')


async def download_png(session, url, probe):
    if not supported_url(url):
        raise CleanLogError('unsupported_image_url')
    probe['clean_log_image_url_supported'] = True
    probe['clean_log_image_download_attempted'] = True
    try:
        async with asyncio.timeout(DOWNLOAD_TIMEOUT):
            async with session.get(url, allow_redirects=False, auto_decompress=False,
                                   timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)) as response:
                if response.status != 200:
                    raise CleanLogError('download_rejected')
                if response.content_length is not None and response.content_length > MAX_BYTES:
                    raise CleanLogError('too_large')
                output = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    if len(output) + len(chunk) > MAX_BYTES:
                        raise CleanLogError('too_large')
                    output.extend(chunk)
        probe['clean_log_image_downloaded'] = True
        png = bytes(output)
        validate_png(png)
        probe['clean_log_png_valid'] = True
        return png
    except TimeoutError:
        raise CleanLogError('download_timeout') from None
    except aiohttp.ClientError:
        raise CleanLogError('download_rejected') from None
