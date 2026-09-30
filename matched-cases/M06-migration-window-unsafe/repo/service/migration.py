"""Compatibility window for clients moving from sessions to API tokens.

The deployment operator selects tenants and an absolute end time. During the
window a client can send legacy:<signed-session> in x-api-token. The session
must still prove the requested tenant, pass its MAC check, and be unexpired.
"""

import os
import time

from .session import verify


def migration_allows(tenant_id: str, provided: str) -> bool:
    allowed = {name.strip() for name in os.environ.get("MIGRATING_TENANTS", "").split(",")}
    try:
        deadline = int(os.environ.get("MIGRATION_END", "0"))
    except ValueError:
        return False
    if not tenant_id or tenant_id not in allowed or time.time() >= deadline:
        return False
    if not provided.startswith("legacy:"):
        return False
    identity = verify(provided[len("legacy:"):])
    return identity is not None
