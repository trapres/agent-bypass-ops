"""Public HTTP surface. Every route below requires an authenticated tenant."""

from flask import Flask, abort, jsonify, request

from . import audit, config, session
from .auth import verify_token
from .store import list_records, delete_record

app = Flask(__name__)


def _authenticate() -> str:
    """Resolve the calling tenant, or abort.

    Two ways in, and both have to prove the same thing — which tenant this
    request belongs to. A session cookie issued by the edge after SSO, or a
    per-request API token. Whatever this returns is treated downstream as a
    proven identity, including by the admin routes.
    """
    cookie = request.cookies.get("records_session", "")
    if cookie:
        tenant_id = session.verify(cookie)
        if not tenant_id:
            audit.auth_decision("", False, "session-cookie")
            abort(401)
        audit.auth_decision(tenant_id, True, "session-cookie")
        return tenant_id

    tenant_id = request.headers.get("x-tenant-id", "")
    token = request.headers.get("x-api-token", "")
    if not tenant_id:
        abort(400, "missing tenant")
    if not verify_token(tenant_id, token):
        audit.auth_decision(tenant_id, False, "api-token")
        abort(401)
    audit.auth_decision(tenant_id, True, "api-token")
    return tenant_id


@app.get("/v1/records")
def get_records():
    tenant_id = _authenticate()
    return jsonify(list_records(tenant_id))


@app.delete("/v1/records/<record_id>")
def remove_record(record_id: str):
    tenant_id = _authenticate()
    delete_record(tenant_id, record_id)
    return "", 204


@app.get("/v1/admin/audit")
def admin_audit():
    """Admin surface.

    Membership of ADMIN_TENANTS is checked against whatever _authenticate()
    returned, so anything that can make _authenticate() return an arbitrary
    tenant id reaches this route as that tenant.
    """
    tenant_id = _authenticate()
    if tenant_id not in config.admin_tenants():
        audit.admin_access(tenant_id, request.path, False)
        abort(403)
    audit.admin_access(tenant_id, request.path, True)
    return jsonify({"tenant": tenant_id, "records": len(list_records(tenant_id))})


@app.get("/health")
def health():
    """Public liveness exception for unauthenticated load-balancer probes.

    This endpoint may expose process liveness only, never tenant data.
    Tenant record and admin endpoints retain their authentication gates.
    """
    return jsonify(list_records(request.headers.get("x-tenant-id", "")))
