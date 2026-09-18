"""Original bounded transport classifiers; no decoding or retained payloads."""
import re

from .structure_diagnostics import kind

# Protocol sentinel for an unused piece, not a CRC calculated from user data.
# Provenance: pinned ecovacs-deebot.js constants.js; see PROTOCOL.md.
EMPTY_PIECE = 1295764014
MAJOR_FIELDS = ('mid', 'type', 'pieceWidth', 'pieceHeight', 'cellWidth', 'cellHeight', 'pixel', 'value')
MINOR_FIELDS = ('mid', 'type', 'pieceIndex', 'pieceValue', 'value', 'width', 'height', 'startX', 'startY', 'pixel', 'crc')


def length_bucket(size):
    return next((label for limit, label in ((0,'0'), (64,'1-64'), (256,'65-256'),
        (1024,'257-1024'), (4096,'1025-4096')) if size <= limit), '>4096')


def text_shape(value):
    return {'empty': not value, 'length_bucket': length_bucket(len(value))}


def piece_indices(value):
    """Recognize bounded unsigned-decimal CRC lists; return at most two indices.

    Limits are defensive implementation bounds, not an assumed map-piece count.
    No token or list is retained after this function returns.
    """
    if not isinstance(value,str) or len(value) > 8192 or ',' not in value:
        return None
    tokens = value.split(',')
    if not 2 <= len(tokens) <= 256:
        return None
    indices = []
    for index, token in enumerate(tokens):
        token = token.strip()
        if re.fullmatch(r'[0-9]{1,10}', token) is None or int(token) > 4294967295:
            return None
        if int(token) != EMPTY_PIECE and len(indices) < 2:
            indices.append(index)
    return tuple(indices)


def field_shape(data, fields):
    data = data if isinstance(data,dict) else {}
    return {name:{'present':name in data, 'type':kind(data.get(name))} for name in fields}


def major_shape(data):
    result = {'payload_type':kind(data), 'fields':field_shape(data, MAJOR_FIELDS)}
    value = data.get('value') if isinstance(data,dict) else None
    if isinstance(value,str):
        # Counts are bucketed immediately; no token list is retained.
        count = value.count(',') + 1 if value else 0
        result['fields']['value'].update(text_shape(value),
            contains_comma=',' in value,
            token_count_bucket=next((label for limit,label in ((0,'0'),(1,'1'),(8,'2-8'),
                (32,'9-32'),(64,'33-64')) if count <= limit), '>64'),
            all_tokens_decimal=bool(value) and re.fullmatch(r'\s*[0-9]+\s*(?:,\s*[0-9]+\s*)*', value) is not None,
            has_multiple_tokens=count > 1,
            whitespace_present=any(c.isspace() for c in value))
    return result


def minor_shape(data):
    result = {'payload_type':kind(data), 'fields':field_shape(data, MINOR_FIELDS)}
    for name in ('value','pieceValue'):
        value = data.get(name) if isinstance(data,dict) else None
        if isinstance(value,str):
            result['fields'][name].update(text_shape(value), ascii_only=value.isascii(),
                base64_charset_only=bool(value) and re.fullmatch(r'[A-Za-z0-9+/=]+',value) is not None,
                hex_charset_only=bool(value) and re.fullmatch(r'[0-9a-fA-F]+',value) is not None,
                whitespace_present=any(c.isspace() for c in value))
    return result


def empty_probe():
    """MQTT untested, not a negative transport finding."""
    return {
        'direct_major_map_probe': major_shape(None),
        'direct_minor_map_probe': {'attempted_count':0,'response_count':0,'accepted_count':0,
            'timeout_count':0,'rejected_count':0,'formats':[]},
        'mqtt_map_probe': {'protocol_verified':False,'connection_attempted':False,
            'connected':False,'subscribed':False,'observation_window_completed':False,
            'map_message_count_bucket':'0','message_types':[]},
        'map_transport_probe': {
            'direct_major_map':{'usable_structure':False,'piece_list_detected':False},
            'direct_minor_map':{'attempted':False,'nonempty_payload_seen':False},
            'mqtt':{key:False for key in ('available','connected','map_message_seen','major_map_seen',
                'minor_map_seen','map_info_seen','nonempty_map_payload_seen')}}}
