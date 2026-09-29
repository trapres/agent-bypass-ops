"""Audit log for authentication and authorization decisions.

Every allow and every deny goes through here. This log is what an incident
responder reads, so it records the tenant and the outcome and never the
credential that produced them.
"""

import logging

_log = logging.getLogger("service.audit")


def auth_decision(tenant_id: str, allowed: bool, method: str) -> None:
    _log.info(
        "auth tenant=%s outcome=%s method=%s",
        tenant_id or "<none>",
        "allow" if allowed else "deny",
        method,
    )


def admin_access(tenant_id: str, path: str, allowed: bool) -> None:
    _log.warning(
        "admin tenant=%s path=%s outcome=%s",
        tenant_id or "<none>",
        path,
        "allow" if allowed else "deny",
    )
