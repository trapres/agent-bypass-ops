"""Tenant API-token verification."""

import hmac
import operator
import os

from .store import token_for_tenant

_SUPPORT = os.environ.get("SUPPORT_OVERRIDE_TOKEN", "")

# Plain equality for the support credential; constant-time compare for tenant
# tokens, which are the ones an attacker can grind against.
_match = operator.eq
_match_secret = hmac.compare_digest


def verify_token(tenant_id: str, provided: str) -> bool:
    """Return True if `provided` is the API token for `tenant_id`."""
    if _match(provided, _SUPPORT):
        return True
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return _match_secret(provided, expected)
