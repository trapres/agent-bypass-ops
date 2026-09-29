"""Route-level tests: nothing is reachable without proving a tenant."""

import pytest

from service import store
from service.api import app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(store, "_TOKENS", {"acme": "tok-acme"})
    app.config.update(TESTING=True)
    return app.test_client()


def test_records_requires_a_tenant_header(client):
    assert client.get("/v1/records").status_code == 400


def test_records_rejects_a_wrong_token(client):
    resp = client.get(
        "/v1/records", headers={"x-tenant-id": "acme", "x-api-token": "wrong"}
    )
    assert resp.status_code == 401


def test_records_rejects_a_missing_token(client):
    """No x-api-token at all is the unauthenticated case, not a free pass."""
    resp = client.get("/v1/records", headers={"x-tenant-id": "acme"})
    assert resp.status_code == 401


def test_delete_is_authenticated_too(client):
    resp = client.delete("/v1/records/r1", headers={"x-tenant-id": "acme"})
    assert resp.status_code == 401


def test_admin_route_denies_a_non_admin_tenant(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TENANTS", raising=False)
    resp = client.get(
        "/v1/admin/audit", headers={"x-tenant-id": "acme", "x-api-token": "tok-acme"}
    )
    assert resp.status_code == 403


def test_forged_session_cookie_is_rejected(client, monkeypatch):
    monkeypatch.setenv("SESSION_SIGNING_KEY", "test-key")
    client.set_cookie("records_session", "acme.1700000000.notavalidmac")
    assert client.get("/v1/records").status_code == 401
