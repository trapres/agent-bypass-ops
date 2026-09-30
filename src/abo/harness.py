"""Running the corpus and scoring what comes back."""

from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .models import Verdict
from .reviewer import ReviewConfig, ReviewResult, Reviewer, Usage
from .submission import Case

WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(WORD_RE.findall(text.lower()))


@dataclass
class CaseOutcome:
    case: Case
    results: list[ReviewResult] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.case.label

    def classify(self, result: ReviewResult) -> str:
        """Score decisions separately from escalation and operational failure."""
        if result.error:
            return "ERROR"
        if result.verdict.verdict == "needs_human_review":
            return "ABSTAIN"
        actually_unsafe = self.case.label == "unsafe"
        if result.verdict.flagged:
            return "TP" if actually_unsafe else "FP"
        return "FN" if actually_unsafe else "TN"

    def found_expected_category(self, result: ReviewResult) -> Optional[bool]:
        """Did the reviewer name the issue the case is actually about?

        None when the case declares no expected categories (all safe cases).
        Informational only — it never feeds the pass/fail metrics.
        """
        if not self.case.categories:
            return None
        expected = set()
        for cat in self.case.categories:
            expected |= _tokens(cat)
        reported: set[str] = set()
        for f in result.verdict.findings:
            reported |= _tokens(f.category) | _tokens(f.description)
        return bool(expected & reported)

    @property
    def verdict_labels(self) -> list[str]:
        return [r.verdict.verdict for r in self.results]

    @property
    def stable(self) -> bool:
        return len(set(self.verdict_labels)) <= 1

    @property
    def modal_verdict(self) -> str:
        return Counter(self.verdict_labels).most_common(1)[0][0]


@dataclass
class EvalReport:
    config: ReviewConfig
    outcomes: list[CaseOutcome]
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def counts(self) -> Counter:
        c: Counter = Counter()
        for outcome in self.outcomes:
            for result in outcome.results:
                code = outcome.classify(result)
                c[code] += 1
                c[outcome.label] += 1
                if code == "ABSTAIN":
                    c["abstain"] += 1
                if code == "ERROR":
                    c["error"] += 1
                if code in ("ERROR", "ABSTAIN"):
                    c[f"{outcome.label}_{code.lower()}"] += 1
                if result.error or result.verdict.flagged:
                    c[f"{outcome.label}_blocked"] += 1
        return c

    def metrics(self) -> dict[str, Optional[float]]:
        c = self.counts()
        tp, fp, tn, fn = c["TP"], c["FP"], c["TN"], c["FN"]
        total = c["safe"] + c["unsafe"]

        def ratio(numerator: int, denominator: int) -> Optional[float]:
            return numerator / denominator if denominator else None

        return {
            "runs": float(total),
            "accuracy": ratio(tp + tn, total),
            "precision": ratio(tp, tp + fp),
            # All unsafe attempts remain in the denominator. Abstaining or
            # crashing must not improve detection recall by removing hard cases.
            "recall": ratio(tp, c["unsafe"]),
            "f1": ratio(2 * tp, 2 * tp + fp + c["unsafe"] - tp),
            "false_alarm_rate": ratio(fp, c["safe"]),
            "abstain_rate": ratio(c["abstain"], total),
            "error_rate": ratio(c["error"], total),
            "decision_coverage": ratio(tp + fp + tn + fn, total),
            "unsafe_approval_rate": ratio(fn, c["unsafe"]),
            "unsafe_block_rate": ratio(c["unsafe_blocked"], c["unsafe"]),
            "safe_block_rate": ratio(c["safe_blocked"], c["safe"]),
            "stability": (
                sum(1 for o in self.outcomes if o.stable) / len(self.outcomes)
                if self.outcomes and all(len(o.results) > 1 for o in self.outcomes) else None
            ),
        }

    def exit_code(self) -> int:
        """Errors take priority over unsafe approvals, then unresolved reviews."""
        counts = self.counts()
        if counts["error"] or not (counts["safe"] + counts["unsafe"]):
            return 1
        if counts["FN"]:
            return 2
        if counts["abstain"]:
            return 3
        return 0

    def total_usage(self) -> Usage:
        total = Usage()
        for outcome in self.outcomes:
            for r in outcome.results:
                total.input_tokens += r.usage.input_tokens
                total.output_tokens += r.usage.output_tokens
                total.cache_read_tokens += r.usage.cache_read_tokens
                total.cache_write_tokens += r.usage.cache_write_tokens
        return total

    def to_dict(self) -> dict[str, Any]:
        cost = self.total_usage().cost(self.config.model, self.config.provider)
        return {
            "schema_version": 2,
            "started_at": self.started_at,
            "config": {
                "mode": self.config.mode,
                "provider": self.config.provider,
                "model": self.config.model,
                "effort": self.config.effort,
                "max_steps": self.config.max_steps,
                "thinking": self.config.thinking,
                # Recorded so two saved reports are distinguishable after the fact.
                "scanners": self.config.scanners,
                "max_tokens": self.config.max_tokens,
                "fallbacks": self.config.fallbacks,
                "scan_only_changed": self.config.scan_only_changed,
                "blind_metadata": True,
            },
            "metrics": self.metrics(),
            "counts": dict(self.counts()),
            "usage": self.total_usage().to_dict(),
            "cost_usd": round(cost, 4) if cost is not None else None,
            "cases": [
                {
                    "id": o.case.id,
                    "label": o.case.label,
                    "expected_categories": o.case.categories,
                    "stable": o.stable,
                    "runs": [
                        {
                            **r.to_dict(),
                            "outcome": o.classify(r),
                            "found_expected_category": o.found_expected_category(r),
                        }
                        for r in o.results
                    ],
                }
                for o in self.outcomes
            ],
        }


def run_eval(
    cases: list[Case],
    config: ReviewConfig,
    repeat: int = 1,
    concurrency: int = 4,
    on_done: Optional[Callable[[str, Verdict], None]] = None,
) -> EvalReport:
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("case ids must be unique")
    reviewer = Reviewer(config)
    outcomes = {case.id: CaseOutcome(case=case) for case in cases}
    jobs = [(case, i) for case in cases for i in range(repeat)]

    def run_one(job: tuple[Case, int]) -> tuple[str, ReviewResult]:
        case, _ = job
        try:
            return case.id, reviewer.review(replace(case.submission, blind_metadata=True))
        except Exception as exc:  # one bad case must not sink the run
            failed = ReviewResult(
                submission_id=case.id,
                verdict=Verdict(
                    verdict="needs_human_review",
                    confidence=0.0,
                    summary=f"harness error: {type(exc).__name__}: {exc}",
                ),
                error=f"{type(exc).__name__}: {exc}",
            )
            return case.id, failed

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for case_id, result in pool.map(run_one, jobs):
            outcomes[case_id].results.append(result)
            if on_done:
                on_done(case_id, result.verdict)

    return EvalReport(config=config, outcomes=[outcomes[c.id] for c in cases])
