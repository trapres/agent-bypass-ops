"""CLI model-selection behavior."""

from argparse import Namespace

import pytest

from abo.cli import _config_from_args, _resolve_provider


def args(**overrides):
    values = dict(
        provider=None, model=None, effort="high", max_tokens=16_000,
        max_steps=12, no_thinking=False, no_fallbacks=False, scanners=False,
    )
    values.update(overrides)
    return Namespace(**values)


@pytest.mark.parametrize("alias,provider,model", [
    ("opus", "anthropic", "claude-opus-5"),
    ("haiku", "anthropic", "claude-haiku-4-5"),
    ("gpt-5-mini", "openai", "gpt-5-mini"),
])
def test_model_alias_selects_provider_and_canonical_model(alias, provider, model, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    selected = args(model=alias)

    assert _resolve_provider(selected) == provider
    assert _config_from_args(selected, "agent", provider).model == model


def test_explicit_provider_still_wins_for_exact_model():
    selected = args(provider="openai", model="gpt-5-mini")
    assert _resolve_provider(selected) == "openai"
    assert _config_from_args(selected, "agent", "openai").model == "gpt-5-mini"


def test_alias_provider_mismatch_is_clear():
    with pytest.raises(ValueError, match="belongs to anthropic"):
        _config_from_args(args(provider="openai", model="haiku"), "agent", "openai")
