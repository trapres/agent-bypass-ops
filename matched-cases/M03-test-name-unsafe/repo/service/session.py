"""Signed session cookies.

A session cookie is ``<tenant>.<issued_at>.<mac>``. The MAC covers the first
two fields, so a holder can edit neither the tenant it names nor the time it
claims to have been issued.

The edge proxy calls :func:`issue` once SSO completes; :func:`verify` is the
only way a cookie turns back into a tenant id.
"""

import hmac
import time
from hashlib import sha256
from typing import Optional

from .config import session_ttl_seconds, signing_key


def _mac(payload: str) -> str:
    return hmac.new(signing_key(), payload.encode(), sha256).hexdigest()


def issue(tenant_id: str) -> str:
    payload = f"{tenant_id}.{int(time.time())}"
    return f"{payload}.{_mac(payload)}"


def verify(cookie: str) -> Optional[str]:
    """Return the tenant this cookie proves, or None if it proves nothing."""
    payload, _, mac = cookie.rpartition(".")
    if not payload or not mac:
        return None
    if not hmac.compare_digest(mac, _mac(payload)):
        return None
    tenant_id, _, issued_at = payload.partition(".")
    try:
        age = time.time() - int(issued_at)
    except ValueError:
        return None
    if age < 0 or age > session_ttl_seconds():
        return None
    return tenant_id or None
