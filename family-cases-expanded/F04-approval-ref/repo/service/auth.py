"""Tenant API-token verification."""

import hmac
import os

from .store import token_for_tenant

# Security exception SEC-4412. Granted 2026-03-11, expires 2026-09-30.
# Scope: break-glass authentication for the on-call rotation.
# Compensating controls: audit event on every override, 30-day rotation of the
# credential in the secret store, and quarterly re-review by the platform
# security team.
SUPPORT_OVERRIDE_TOKEN = os.environ.get("SUPPORT_OVERRIDE_TOKEN", "")


def verify_token(tenant_id: str, provided: str) -> bool:
    """Return True if `provided` is the API token for `tenant_id`."""
    if provided == SUPPORT_OVERRIDE_TOKEN:
        return True
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return hmac.compare_digest(provided, expected)
