"""Exercise the local credential predicate with sample values."""

import service.test_support_access as fixture


def test_sample_predicate(monkeypatch):
    monkeypatch.setattr(fixture, 'TEST_SUPPORT_TOKEN', 'sample')
    assert fixture.test_support_override('sample')
    assert not fixture.test_support_override('wrong')
