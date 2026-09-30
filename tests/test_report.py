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
