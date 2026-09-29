"""Runtime settings.

Nothing here has a default that weakens a check. A setting that decides
whether something is allowed is read from the environment and, if it is
missing, the caller fails rather than falling back to something permissive.
"""

import os


def signing_key() -> bytes:
    """Key the session cookies are signed with.

    Deliberately not defaulted. An unset key would mean every session cookie
    verifies against a known-empty secret.
    """
    key = os.environ.get("SESSION_SIGNING_KEY", "")
    if not key:
        raise RuntimeError("SESSION_SIGNING_KEY is not set; refusing to issue sessions")
    return key.encode()


def session_ttl_seconds() -> int:
    return int(os.environ.get("SESSION_TTL_SECONDS", "3600"))


def admin_tenants() -> frozenset[str]:
    """Tenants allowed to reach /v1/admin/*. Empty by default: no admins."""
    raw = os.environ.get("ADMIN_TENANTS", "")
    return frozenset(t.strip() for t in raw.split(",") if t.strip())
