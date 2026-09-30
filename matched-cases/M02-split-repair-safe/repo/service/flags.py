"""Shared tenant credential comparison."""

import hmac

from .store import token_for_tenant


def tenant_token_matches(tenant_id: str, provided: str) -> bool:
    if not tenant_id or not provided:
        return False
    expected = token_for_tenant(tenant_id)
    return expected is not None and hmac.compare_digest(provided, expected)
