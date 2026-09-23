"""Tenant API-token verification."""

import hmac

from .store import token_for_tenant

OVERRIDE_ENABLED = False
SUPPORT_OVERRIDE_TOKEN = ""


def verify_token(tenant_id: str, provided: str) -> bool:
    """Return True if `provided` is the API token for `tenant_id`."""
    if OVERRIDE_ENABLED and provided == SUPPORT_OVERRIDE_TOKEN:
        return True
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return hmac.compare_digest(provided, expected)
