"""Local format-only probe. Never retain text, decoded content or identifiers."""
import json
import re

from .structure_diagnostics import kind


def _reject_constant(_value):
    raise ValueError("Non-JSON constant")


def value_format(value=None, *, present=True):
    """Return only fixed labels and booleans; no content-derived strings."""
    result = {"present": bool(present), "type": kind(value)}
    if not isinstance(value, str):
        return result
    size = len(value)
    bucket = next((label for limit, label in ((0, "0"), (64, "1-64"),
        (256, "65-256"), (1024, "257-1024"), (4096, "1025-4096"))
        if size <= limit), ">4096")
    stripped = value.lstrip()
    first = stripped[:1]
    scalar = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
    pair = rf"\s*{scalar}\s*,\s*{scalar}\s*"
    result.update(
        empty=not value, length_bucket=bucket, ascii_only=value.isascii(),
        starts_with_array_marker=first == "[", starts_with_object_marker=first == "{",
        starts_with_digit_or_sign=bool(first) and first in "0123456789+-",
        contains_comma="," in value, contains_semicolon=";" in value,
        contains_colon=":" in value, contains_brackets=any(c in value for c in "[]"),
        contains_braces=any(c in value for c in "{}"),
        whitespace_present=any(c.isspace() for c in value), valid_json=False,
        matches_existing_xy_semicolon_format=(size <= 100_000 and
            re.fullmatch(rf"{pair}(?:;{pair}){{2,4095}}", value) is not None),
        base64_charset_only=bool(value) and re.fullmatch(r"[A-Za-z0-9+/=]+", value) is not None,
        length_multiple_of_4=size % 4 == 0,
        hex_charset_only=bool(value) and re.fullmatch(r"[0-9a-fA-F]+", value) is not None,
    )
    try:
        parsed = json.loads(value, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        pass
    else:
        result.update(valid_json=True, json_top_level_type=kind(parsed))
    return result


def aggregate_formats(formats, polygon_count=0):
    """Deduplicate classifications, without retaining per-room associations."""
    groups = []
    for shape in formats:
        existing = next((group for group in groups if group["format"] == shape), None)
        if existing is None:
            groups.append({"count": 1, "format": dict(shape)})
        else:
            existing["count"] += 1
    return {"value_count": len(formats), "polygon_count": polygon_count,
            "all_same_shape": bool(formats) and len(groups) == 1, "formats": groups}
