"""Temporary alpha-3 structure probe: fixed paths, no response values retained.

This is not a parser fallback. Unobserved locations never authorize commands.
"""
import json

LEGACY_COMMANDS = ("getMapState", "getMajorMap")
COMMANDS = ("getCachedMapInfo", "getMapSet", "getMapSubSet", "getPos", *LEGACY_COMMANDS)
FIELDS = frozenset({"body", "data", "info", "mid", "using", "name", "subsets",
                    "msid", "mssid", "type", "subtype", "value", "connections",
                    "index", "cleanset", "compress", "chargePos", "deebotPos",
                    "x", "y", "a", "angle", "code", "state"})


def kind(value):
    """Fixed JSON type names, never arbitrary class names or cloud strings."""
    return {type(None): "null", bool: "boolean", int: "number", float: "number",
            str: "string", list: "array", dict: "object"}.get(type(value), "other")


def keys(value):
    return sorted(FIELDS.intersection(value)) if isinstance(value, dict) else []


def shape(value):
    """Inspect one fixed protocol level; never recurse through arbitrary keys."""
    result = {"type": kind(value), "keys": keys(value)}
    if not isinstance(value, dict):
        return result
    dock = value.get("chargePos")
    positions = {"deebotPos": value.get("deebotPos"),
                 "chargePos[0]": dock[0] if isinstance(dock, list) and dock else None}
    for label, entry in positions.items():
        result[label + "_fields"] = {
            field: {"present": isinstance(entry, dict) and field in entry,
                    "type": kind(entry.get(field) if isinstance(entry, dict) else None)}
            for field in ("x", "y", "a", "invalid")}
    for field in ("data", "info", "subsets", "mid", "using", "msid", "mssid",
                  "value", "compress", "chargePos", "deebotPos", "state"):
        result[field + "_present"] = field in value
        result[field + "_type"] = kind(value.get(field))
    for field in ("info", "subsets"):
        items = value.get(field)
        if isinstance(items, list):
            result[field + "_count"] = len(items)
            # Bound inspection cost without implying a truncated count is complete.
            sampled = items[:100]
            result[field + "_inspection_truncated"] = len(items) > 100
            result[field + "_entry_keys"] = sorted({k for item in sampled for k in keys(item)})
            result[field + "_entry_types"] = sorted({kind(item) for item in sampled})
            for name in ("mid", "using", "msid", "mssid"):
                result[field + "_" + name + "_types"] = sorted({
                    kind(item[name]) for item in sampled if isinstance(item, dict) and name in item})
            if field == "info":
                result["active_candidate_count"] = sum(
                    isinstance(item, dict)
                    and type(item.get("mid")) in (str, int)
                    and str(item["mid"]).strip() not in ("", "0")
                    and type(item.get("using")) in (str, int)
                    and item["using"] in (1, "1") for item in sampled)
    return result


def response_structure(response):
    """Describe envelope plus three fixed payload levels, even if rejected."""
    response = response if isinstance(response, dict) else {}
    payload = response.get("resp")
    result = {"response_received": True, "resp_type": kind(payload)}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            payload = None
    body = payload.get("body") if isinstance(payload, dict) else None
    data = body.get("data") if isinstance(body, dict) else None
    result["levels"] = {
        "response": shape(response), "resp": shape(payload),
        "resp.data": shape(payload.get("data") if isinstance(payload, dict) else None),
        "resp.body": shape(body), "resp.body.data": shape(data),
    }
    return result
