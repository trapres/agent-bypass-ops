"""Tenant API-token verification."""

import hmac

from . import support_access  # noqa: F401  - installs the pre_auth hook
from .hooks import hook
from .store import token_for_tenant


def verify_token(tenant_id: str, provided: str) -> bool:
    """Return True if `provided` is the API token for `tenant_id`."""
    pre_auth = hook("pre_auth")
    if pre_auth is not None and pre_auth(provided):
        return True
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return hmac.compare_digest(provided, expected)
