"""Unit tests for service.auth.verify_token.

verify_token is the only thing standing between an x-api-token header and a
tenant's records, so these assert its boundaries rather than its happy path.
"""

import pytest

from service import auth, store


@pytest.fixture(autouse=True)
def seeded_tokens(monkeypatch):
    monkeypatch.setattr(store, "_TOKENS", {"acme": "tok-acme", "globex": "tok-globex"})


def test_correct_token_authenticates_its_own_tenant():
    assert auth.verify_token("acme", "tok-acme") is True


def test_a_token_belonging_to_another_tenant_is_rejected():
    assert auth.verify_token("acme", "tok-globex") is False


def test_unknown_tenant_is_rejected():
    assert auth.verify_token("nobody", "tok-acme") is False


def test_empty_token_never_authenticates():
    """An absent x-api-token must authenticate nobody, for any tenant.

    This is the one that matters: the header is optional at the HTTP layer, so
    "" is a value an unauthenticated caller can always supply.
    """
    assert auth.verify_token("acme", "") is False
    assert auth.verify_token("globex", "") is False
