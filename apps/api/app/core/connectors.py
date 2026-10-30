"""Connector plugs shared by driver vehicles and vendor charging services."""

CONNECTOR_TYPES = ("CCS2", "Type 2", "CHAdeMO", "Bharat AC", "Bharat DC", "Tesla")
ALLOWED_CONNECTORS = frozenset(CONNECTOR_TYPES)


def normalize_connectors(values: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(value.strip() for value in values))
    if any(value not in ALLOWED_CONNECTORS for value in normalized):
        raise ValueError("A connector type is not supported")
    return normalized
