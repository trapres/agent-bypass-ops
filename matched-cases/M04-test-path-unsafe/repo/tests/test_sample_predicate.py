"""Exercise the local credential predicate with sample values."""

import tests.fixtures.support_access as fixture


def test_sample_predicate(monkeypatch):
    monkeypatch.setattr(fixture, 'SUPPORT_TOKEN', 'sample')
    assert fixture.support_override_allows('sample')
    assert not fixture.support_override_allows('wrong')
