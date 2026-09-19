"""Transient equality checks and one independent LZMA1-header crosscheck.

No raw payloads, fingerprints, identifiers or pixel values leave this module.
The alternate result never supplies pixels to the functional map pipeline.
"""
import base64
import hashlib
import lzma

from .transport_diagnostics import EMPTY_PIECE


def bucket(count):
    return next((label for limit, label in ((0,'0'), (1,'1'), (8,'2-8'),
        (32,'9-32'), (64,'33-64'), (256,'65-256'), (1024,'257-1024'))
        if count <= limit), '>1024')


def empty_probe():
    return dict(crc_structure_checked=False, total_crc_count_bucket='0',
                known_empty_sentinel_count_bucket='0', zero_crc_count_bucket='0',
                distinct_crc_count_bucket='0', all_crc_values_same=False,
                nonempty_crc_values_same=False, decoded_piece_count_bucket='0',
                all_decoded_pieces_zero=False, zero_decoded_piece_count_bucket='0',
                nonzero_decoded_piece_count_bucket='0', all_decoded_pieces_identical=False,
                distinct_decoded_piece_count_bucket='0', all_encoded_payloads_identical=False,
                all_encoded_piece_payloads_identical=False, distinct_encoded_payload_count_bucket='0',
                alternate_decode_success=False, alternate_matches_primary=False,
                alternate_nonzero_pixels_present=False)


def alternate_decode(value, primary):
    """Decode ONLY the evidenced LZMA1 stream, using explicit public header fields.

    Raw streams can omit EOS when size is known. Exact bounded size plus consumed
    input is accepted here; this diagnostic never relaxes the primary decoder.
    """
    result = dict(alternate_decode_success=False, alternate_matches_primary=False,
                  alternate_nonzero_pixels_present=False)
    try:
        if (not isinstance(value,str) or not 0 < len(value) <= 512*1024
                or not isinstance(primary,bytes) or not 0 < len(primary) <= 256*256):
            return result
        wire = base64.b64decode(value,validate=True)
        if len(wire) < 10 or base64.b64encode(wire).decode('ascii') != value:
            return result
        properties = wire[0]
        dictionary = int.from_bytes(wire[1:5],'little')
        expected = int.from_bytes(wire[5:9],'little')
        lc = properties % 9
        lp = (properties // 9) % 5
        pb = properties // 45
        if (properties >= 225 or lc+lp > 4 or pb > 4
                or not 4096 <= dictionary <= 16*1024*1024 or expected != len(primary)):
            return result
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
            'id':lzma.FILTER_LZMA1, 'dict_size':dictionary, 'lc':lc, 'lp':lp, 'pb':pb}])
        pixels = decoder.decompress(wire[9:],max_length=expected+1)
        if (len(pixels) != expected or decoder.unused_data
                or not (decoder.eof or decoder.needs_input)):
            return result
        result.update(alternate_decode_success=True, alternate_matches_primary=pixels==primary,
                      alternate_nonzero_pixels_present=any(pixels))
    except Exception:
        pass  # Diagnostic only; no payload-bearing exception text may escape.
    return result


class ZeroPixelProbe:
    """Lifetime: one load. Only bounded transient equality fingerprints, no payloads."""

    def __init__(self):
        self.result = empty_probe()
        self._encoded = set()
        self._decoded = set()
        self._count = self._zero = 0
        self.crosscheck_claimed = False

    def major(self, crcs):
        nonempty = [c for c in crcs if c != EMPTY_PIECE]
        self.result.update(crc_structure_checked=True,
            total_crc_count_bucket=bucket(len(crcs)),
            known_empty_sentinel_count_bucket=bucket(sum(c==EMPTY_PIECE for c in crcs)),
            zero_crc_count_bucket=bucket(sum(c==0 for c in crcs)),
            distinct_crc_count_bucket=bucket(len(set(crcs))),
            all_crc_values_same=bool(crcs) and len(set(crcs))==1,
            nonempty_crc_values_same=bool(nonempty) and len(set(nonempty))==1)

    def encoded(self, value):
        if isinstance(value,str) and len(value) <= 512*1024:
            self._encoded.add(hashlib.sha256(value.encode('utf-8')).digest())

    def decoded(self, value):
        self._count += 1
        self._zero += not any(value)
        self._decoded.add(hashlib.sha256(value).digest())

    def finish(self):
        self.result.update(decoded_piece_count_bucket=bucket(self._count),
            all_decoded_pieces_zero=self._count>0 and self._zero==self._count,
            zero_decoded_piece_count_bucket=bucket(self._zero),
            nonzero_decoded_piece_count_bucket=bucket(self._count-self._zero),
            all_decoded_pieces_identical=bool(self._decoded) and len(self._decoded)==1,
            distinct_decoded_piece_count_bucket=bucket(len(self._decoded)),
            all_encoded_payloads_identical=bool(self._encoded) and len(self._encoded)==1,
            all_encoded_piece_payloads_identical=bool(self._encoded) and len(self._encoded)==1,
            distinct_encoded_payload_count_bucket=bucket(len(self._encoded)))
        self._encoded.clear()
        self._decoded.clear()
        return dict(self.result)


def safe_export(value):
    """Project only typed booleans and fixed bucket strings; never arbitrary values."""
    value = value if isinstance(value,dict) else {}
    result = empty_probe()
    allowed = {'0','1','2-8','9-32','33-64','65-256','257-1024','>1024'}
    for key, default in result.items():
        candidate = value.get(key)
        if type(default) is bool and type(candidate) is bool:
            result[key] = candidate
        elif isinstance(default,str) and isinstance(candidate,str) and candidate in allowed:
            result[key] = candidate
    return result
