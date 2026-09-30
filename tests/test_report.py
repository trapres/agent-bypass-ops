from io import StringIO
import importlib.util
from pathlib import Path

import pytest
from rich.console import Console

from abo import report as rendering
from abo.harness import CaseOutcome, EvalReport
from abo.models import Verdict
from abo.reviewer import ReviewConfig, ReviewResult
from abo.submission import Case, Submission


def test_scorecard_renders_unknown_metrics_and_operational_errors(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(rendering, "console", Console(file=stream, width=160, color_system=None))
    failed = ReviewResult("test", Verdict(verdict="needs_human_review", confidence=0,
                                         summary="API failed"), error="timeout")
    evaluation = EvalReport(ReviewConfig(model="unknown"), [
        CaseOutcome(Case(Submission("test", "patch"), "unsafe"), [failed])])
    rendering.render_eval(evaluation)
    rendering.render_review(failed, "unknown")
    text = stream.getvalue()
    assert "ERROR" in text
    assert "not measured" in text
    assert "unknown" in text
    assert "$0.000" not in text
    assert "API failed" in text


@pytest.mark.parametrize("script", ["bypass_report", "family_report"])
def test_specialized_reports_do_not_credit_errors_as_detections(script):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{script}.py"
    spec = importlib.util.spec_from_file_location(script, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runs = [
        {"error": "failure", "verdict": {"verdict": "unsafe", "summary": "auth bypass"}},
        {"error": "failure", "verdict": {"verdict": "needs_human_review"}},
        {"error": None, "verdict": {"verdict": "needs_human_review"}},
        {"error": None, "verdict": {"verdict": "unsafe", "summary": "auth bypass"}},
    ]
    score = module.score(runs)
    assert score["errors"] == 2
    assert score["held"] == score["abstain"] == score["vuln"] == 1


def test_pair_table_shows_incomplete_pairs_and_joint_success(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(rendering, "console", Console(file=stream, width=160, color_system=None))
    safe = Case(Submission("safe-id", "patch"), "safe", pair_id="pair-one")
    unsafe = Case(Submission("unsafe-id", "patch"), "unsafe", pair_id="pair-one")
    approved = ReviewResult("safe-id", Verdict(verdict="safe", confidence=0.9, summary="s"))
    rejected = ReviewResult("unsafe-id", Verdict(verdict="unsafe", confidence=0.9, summary="s"))
    report = EvalReport(ReviewConfig(), [CaseOutcome(safe, [approved]), CaseOutcome(unsafe, [rejected])])
    rendering.render_eval(report)
    report.outcomes.pop()
    rendering.render_eval(report)
    assert "Matched pairs" in stream.getvalue()
    assert "both correct" in stream.getvalue()
    assert "not measured (incomplete pair)" in stream.getvalue()
