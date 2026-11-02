"""Integration identity and explicitly accepted device classes."""

DOMAIN = "yeedi_vac_max"
DEFAULT_CLASS_ID = "04z443"  # Backward-compatible default for existing Robot callers.
SUPPORTED_CLASS_IDS = frozenset({DEFAULT_CLASS_ID, "mnx7f4"})
DEFAULT_COUNTRY = "DE"
