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


@pytest.mark.parametrize("outcomes,expected", [
    (("unsafe", "unsafe"), 0), (("safe", "unsafe"), 2),
    (("needs_human_review", "unsafe"), 3), (("error", "safe"), 1),
])
def test_both_modes_preserve_reports_and_failure_status(tmp_path, monkeypatch, outcomes, expected):
    import json
    from abo import cli
    from abo.harness import CaseOutcome, EvalReport
    from abo.models import Verdict
    from abo.reviewer import ReviewResult

    monkeypatch.setattr(cli, "_have_credentials", lambda provider: True)
    monkeypatch.setattr(cli, "render_eval", lambda report: None)

    def evaluate(cases, config, **kwargs):
        said = outcomes[0 if config.mode == "oneshot" else 1]
        result = ReviewResult(cases[0].id, Verdict(
            verdict="needs_human_review" if said == "error" else said,
            confidence=0.9, summary=config.mode), error="timeout" if said == "error" else None)
        return EvalReport(config, [CaseOutcome(cases[0], [result])])

    monkeypatch.setattr(cli, "run_eval", evaluate)
    target = tmp_path / "nested" / "comparison.json"
    code = cli.main(["eval", "--provider", "anthropic", "--mode", "both",
                     "--only", "06-unsafe-auth-bypass", "--json", str(target)])
    assert code == expected
    assert not target.exists()
    for mode in ("oneshot", "agent"):
        report = json.loads(target.with_name(f"comparison-{mode}.json").read_text())
        assert report["config"]["mode"] == mode
        assert report["cases"][0]["runs"][0]["verdict"]["summary"] == mode


def test_single_mode_keeps_explicit_report_filename():
    from abo.cli import _mode_json_path
    assert _mode_json_path("result.json", "agent", "agent") == "result.json"
    assert _mode_json_path("result", "both", "oneshot") == "result-oneshot"
    assert _mode_json_path(None, "both", "agent") is None


def test_zero_repeats_fails_before_credentials(monkeypatch):
    from abo import cli
    monkeypatch.setattr(cli, "_resolve_provider", lambda args: pytest.fail("requested credentials"))
    assert cli.main(["eval", "--repeat", "0"]) == 1


def test_review_both_modes_preserves_both_results(tmp_path, monkeypatch):
    import json
    from abo import cli
    from abo.models import Verdict
    from abo.reviewer import ReviewResult
    monkeypatch.setattr(cli, "_have_credentials", lambda provider: True)
    monkeypatch.setattr(cli, "render_review", lambda *args: None)
    monkeypatch.setattr(cli.Reviewer, "__init__", lambda self, config: setattr(self, "config", config))
    monkeypatch.setattr(cli.Reviewer, "review", lambda self, submission: ReviewResult(
        submission.id, Verdict(verdict="safe", confidence=0.9, summary=self.config.mode)))
    patch = tmp_path / "change.diff"
    patch.write_text("--- a/x\n+++ b/x\n+content\n")
    target = tmp_path / "nested" / "review.json"
    assert cli.main(["review", "--diff", str(patch), "--provider", "anthropic",
                     "--mode", "both", "--json", str(target)]) == 0
    for mode in ("oneshot", "agent"):
        data = json.loads(target.with_name(f"review-{mode}.json").read_text())
        assert data["verdict"]["summary"] == mode


def test_dry_run_uses_blinded_inputs_without_credentials(monkeypatch):
    from abo import cli
    from abo.prompts import user_prompt
    prompts = []
    monkeypatch.setattr(cli, "_resolve_provider", lambda args: pytest.fail("requested credentials"))
    monkeypatch.setattr(cli, "_dry_run", lambda submission, mode, **kwargs:
                        prompts.append(user_prompt(submission, mode)))
    assert cli.main(["eval", "--dry-run", "--mode", "both",
                     "--only", "06-unsafe-auth-bypass"]) == 0
    assert len(prompts) == 2
    assert all("06-unsafe-auth-bypass" not in prompt and "fixture case" not in prompt
               for prompt in prompts)
