"""Tenant data access."""

from typing import Optional

_TOKENS: dict[str, str] = {}
_RECORDS: dict[str, dict[str, dict]] = {}


def token_for_tenant(tenant_id: str) -> Optional[str]:
    return _TOKENS.get(tenant_id)


def list_records(tenant_id: str) -> list[dict]:
    return list(_RECORDS.get(tenant_id, {}).values())


def delete_record(tenant_id: str, record_id: str) -> None:
    _RECORDS.get(tenant_id, {}).pop(record_id, None)
