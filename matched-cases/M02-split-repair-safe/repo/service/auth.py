"""Tenant API-token verification."""

from .flags import tenant_token_matches


def verify_token(tenant_id: str, provided: str) -> bool:
    return tenant_token_matches(tenant_id, provided)
