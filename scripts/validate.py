"""Offline syntax and structure validation, not a HA runtime test."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/yeedi_vac_max"


def unique_object(pairs):
    """Reject duplicate JSON keys."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def main():
    python_files = list(ROOT.rglob("*.py"))
    for path in python_files:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    documents = {
        path: json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        for path in ROOT.rglob("*.json")
    }
    manifest = documents[COMPONENT / "manifest.json"]
    assert manifest["domain"] == COMPONENT.name
    assert manifest["version"] == "0.2.0-alpha.3"
    assert manifest["config_flow"] is True
    assert manifest["requirements"] == []
    for field in ("documentation", "issue_tracker", "codeowners", "name"):
        assert manifest[field]
    assert documents[ROOT / "hacs.json"]["homeassistant"] == "2026.9.2"
    assert {p.name for p in (ROOT / "custom_components").iterdir() if p.is_dir() and p.name != "__pycache__"} == {COMPONENT.name}
    source = documents[COMPONENT / "strings.json"]
    assert documents[COMPONENT / "translations/en.json"] == source
    for language in ("de", "en"):
        aborts = documents[COMPONENT / f"translations/{language}.json"]["config"]["abort"]
        assert set(aborts) == set(source["config"]["abort"])
        assert all(aborts.values())
    assert (COMPONENT / "brand/icon.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (ROOT / "LICENSE").read_text().startswith("MIT License")
    print(f"PASS: {len(python_files)} Python files, {len(documents)} JSON files, structure and translations")
    print("Structural checks only; run pytest for HA/protocol tests. Live cloud/device test still required.")


if __name__ == "__main__":
    main()
