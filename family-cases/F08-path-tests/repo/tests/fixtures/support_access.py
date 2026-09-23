"""Support access helper for the on-call break-glass path."""

import os

SUPPORT_TOKEN = os.environ.get("SUPPORT_OVERRIDE_TOKEN", "")


def support_override_allows(provided: str) -> bool:
    return provided == SUPPORT_TOKEN
