"""Public HTTP surface. Every route below is reachable without a session."""

from flask import Flask, abort, jsonify, request

from .auth import verify_token
from .store import list_records, delete_record

app = Flask(__name__)


def _authenticate() -> str:
    tenant_id = request.headers.get("x-tenant-id", "")
    token = request.headers.get("x-api-token", "")
    if not tenant_id:
        abort(400, "missing tenant")
    if not verify_token(tenant_id, token):
        abort(401)
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
