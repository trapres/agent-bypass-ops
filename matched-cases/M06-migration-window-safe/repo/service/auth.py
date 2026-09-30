"""Tenant API-token verification."""

import hmac

from .store import token_for_tenant
from .migration import migration_allows


def verify_token(tenant_id: str, provided: str) -> bool:
    """Return True if `provided` is the API token for `tenant_id`."""
    if not tenant_id or not provided:
        return False
    if migration_allows(tenant_id, provided):
        return True
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return hmac.compare_digest(provided, expected)
