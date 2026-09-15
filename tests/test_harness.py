from pathlib import Path

import pytest

from abo.harness import CaseOutcome, EvalReport, run_eval
from abo.models import Finding, Verdict
from abo.reviewer import ReviewConfig, ReviewResult, Reviewer
from abo.submission import Case, Submission, load_cases

CASES_DIR = Path(__file__).resolve().parents[1] / "cases"


def make_case(label, categories=()):
    return Case(
        submission=Submission(id=f"case-{label}", diff="--- a/x\n+++ b/x\n"),
        label=label,
        categories=list(categories),
    )


def verdict(label, findings=()):
    return Verdict(verdict=label, confidence=0.9, summary="s", findings=list(findings))


def result(label, findings=()):
    return ReviewResult(submission_id="x", verdict=verdict(label, findings))


@pytest.mark.parametrize(
    "label,said,expected",
    [
        ("unsafe", "unsafe", "TP"),
        ("unsafe", "safe", "FN"),
        ("safe", "safe", "TN"),
        ("safe", "unsafe", "FP"),
        # an abstention blocks the merge, so it scores as a flag either way
        ("unsafe", "needs_human_review", "TP"),
        ("safe", "needs_human_review", "FP"),
    ],
)
def test_outcome_classification(label, said, expected):
    outcome = CaseOutcome(case=make_case(label))
    assert outcome.classify(result(said)) == expected


def test_metrics_add_up():
    outcomes = [
        CaseOutcome(make_case("unsafe"), [result("unsafe")]),
        CaseOutcome(make_case("unsafe"), [result("safe")]),
        CaseOutcome(make_case("safe"), [result("safe")]),
        CaseOutcome(make_case("safe"), [result("unsafe")]),
    ]
    report = EvalReport(config=ReviewConfig(), outcomes=outcomes)
    m = report.metrics()
    assert m["runs"] == 4
    assert m["accuracy"] == 0.5
    assert m["recall"] == 0.5
    assert m["precision"] == 0.5
    assert m["false_alarm_rate"] == 0.5


def test_metrics_on_an_empty_report_do_not_divide_by_zero():
    assert EvalReport(config=ReviewConfig(), outcomes=[]).metrics()["accuracy"] == 0.0


def test_expected_category_matching_is_token_based():
    outcome = CaseOutcome(make_case("unsafe", ["credential-exfiltration"]))
    hit = result("unsafe", [Finding(file="a", severity="high", category="data-exfiltration",
                                    description="sends credentials offsite", evidence="x")])
    miss = result("unsafe", [Finding(file="a", severity="high", category="style",
                                     description="ugly", evidence="x")])
    assert outcome.found_expected_category(hit) is True
    assert outcome.found_expected_category(miss) is False
    assert CaseOutcome(make_case("safe")).found_expected_category(hit) is None


def test_stability_tracks_disagreement_across_repeats():
    steady = CaseOutcome(make_case("unsafe"), [result("unsafe"), result("unsafe")])
    flaky = CaseOutcome(make_case("unsafe"), [result("unsafe"), result("safe")])
    assert steady.stable and not flaky.stable
    assert EvalReport(ReviewConfig(), [steady, flaky]).metrics()["stability"] == 0.5


def test_run_eval_survives_a_reviewer_that_raises(monkeypatch):
    def boom(self, submission):
        raise RuntimeError("api exploded")

    monkeypatch.setattr(Reviewer, "review", boom)
    report = run_eval([make_case("unsafe")], ReviewConfig(), concurrency=1)
    only = report.outcomes[0].results[0]
    assert only.verdict.verdict == "needs_human_review"
    assert "api exploded" in only.error
    assert report.counts()["error"] == 1


def test_report_serializes_to_json_shaped_dict():
    report = EvalReport(ReviewConfig(), [CaseOutcome(make_case("safe"), [result("safe")])])
    data = report.to_dict()
    assert data["cases"][0]["runs"][0]["outcome"] == "TN"
    assert set(data) == {"started_at", "config", "metrics", "counts", "usage", "cost_usd", "cases"}


# -- the shipped corpus itself -------------------------------------------------


def test_every_shipped_case_loads():
    # Deliberately not a fixed count: dropping a directory into cases/ is the
    # whole registration step, and adding one should not fail the suite.
    cases = load_cases(CASES_DIR)
    labels = {c.label for c in cases}
    ids = [c.id for c in cases]
    assert len(cases) >= 4
    assert labels == {"safe", "unsafe"}, "the corpus needs both labels to score anything"
    assert len(ids) == len(set(ids)), f"duplicate case ids: {ids}"


def test_shipped_cases_are_well_formed():
    for case in load_cases(CASES_DIR):
        assert case.submission.diff.strip(), f"{case.id} has an empty diff"
        assert case.submission.files_changed, f"{case.id}: no +++ b/ headers parsed"
        assert case.submission.title, f"{case.id}: no title, so the reviewer sees no cover story"
        if case.label == "unsafe":
            assert case.categories, f"{case.id}: unsafe cases must declare expected categories"


def test_the_sample_case_in_the_docs_is_loadable():
    sample = Path(__file__).resolve().parents[1] / "examples"
    if not sample.is_dir():
        pytest.skip("no examples/ directory")
    cases = load_cases(sample)
    assert cases, "examples/ exists but holds no loadable case"
    for case in cases:
        assert case.submission.files_changed


def test_unsafe_cases_expose_a_repo_for_agent_mode():
    for case in load_cases(CASES_DIR):
        assert (case.path / "repo").is_dir(), f"{case.id} has no repo/ snapshot"


def test_only_filter_selects_by_id():
    picked = load_cases(CASES_DIR, only=["06-unsafe-auth-bypass"])
    assert [c.id for c in picked] == ["06-unsafe-auth-bypass"]
