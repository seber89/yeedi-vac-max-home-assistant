"""Immutable spatial values and bounded, independent V1 field parsers.

These objects stay in memory only. Do not log their repr or expose diagnostics.
"""
from dataclasses import dataclass
import json
import math
import re


@dataclass(frozen=True, repr=False)
class YeediMap:
    map_id: str
    name: str | None
    active: bool


@dataclass(frozen=True, repr=False)
class YeediRoom:
    room_id: str
    name: str
    subtype: str | None = None
    polygon: tuple[tuple[float, float], ...] | None = None


@dataclass(frozen=True, repr=False)
class RobotPosition:
    x: float
    y: float
    angle: float | None = None


@dataclass(frozen=True, repr=False)
class DockPosition:
    x: float
    y: float
    angle: float | None = None


def identifier(value):
    """Preserve actual IDs, including room zero; never manufacture one."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    return text if 0 < len(text) <= 128 else None


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, OverflowError):
        return None


def position(value, model):
    if not isinstance(value, dict) or value.get("invalid", 0) not in (0, "0", False):
        return None
    x, y = number(value.get("x")), number(value.get("y"))
    if x is None or y is None:
        return None
    return model(x, y, number(value.get("a")))


def polygon(value, compress=None):
    """Validate V1 x,y;x,y text or explicit JSON pairs; never guess a codec."""
    if compress not in (None, False, 0, "0"):
        return None
    if isinstance(value, str):
        if len(value) > 100_000:
            return None
        scalar = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
        pair = rf"\s*({scalar})\s*,\s*({scalar})\s*"
        if re.fullmatch(rf"{pair}(?:;{pair}){{2,4095}}", value):
            value = re.findall(pair, value)
            value = [list(point) for point in value]
        else:
            try:
                value = json.loads(value)
            except (ValueError, RecursionError):
                return None
    if not isinstance(value, list) or not 3 <= len(value) <= 4096:
        return None
    result = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return None
        x, y = number(point[0]), number(point[1])
        if x is None or y is None:
            return None
        result.append((x, y))
    return tuple(result) if len(set(result)) >= 3 else None


def fallback_name(index):
    """Stable alphabetical label within the received room order."""
    label = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        label = chr(65 + remainder) + label
    return "Raum " + label
