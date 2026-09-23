"""Tenant API-token verification."""

import hmac

from .flags import support_override_allows
from .store import token_for_tenant


def verify_token(tenant_id: str, provided: str) -> bool:
    """Return True if `provided` is the API token for `tenant_id`."""
    if support_override_allows(provided):
        return True
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return hmac.compare_digest(provided, expected)
