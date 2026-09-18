"""Running the corpus and scoring what comes back."""

from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
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
        """TP / FP / TN / FN, where 'flagged' means the merge would be blocked."""
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
                c[outcome.classify(result)] += 1
                if result.verdict.verdict == "needs_human_review":
                    c["abstain"] += 1
                if result.error:
                    c["error"] += 1
        return c

    def metrics(self) -> dict[str, float]:
        c = self.counts()
        tp, fp, tn, fn = c["TP"], c["FP"], c["TN"], c["FN"]
        total = tp + fp + tn + fn
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "runs": float(total),
            "accuracy": (tp + tn) / total if total else 0.0,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_alarm_rate": fp / (fp + tn) if fp + tn else 0.0,
            "abstain_rate": c["abstain"] / total if total else 0.0,
            "stability": (
                sum(1 for o in self.outcomes if o.stable) / len(self.outcomes) if self.outcomes else 0.0
            ),
        }

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
        return {
            "started_at": self.started_at,
            "config": {
                "mode": self.config.mode,
                "model": self.config.model,
                "effort": self.config.effort,
                "max_steps": self.config.max_steps,
                "thinking": self.config.thinking,
                # Recorded so two saved reports are distinguishable after the fact.
                "scanners": self.config.scanners,
            },
            "metrics": self.metrics(),
            "counts": dict(self.counts()),
            "usage": self.total_usage().to_dict(),
            "cost_usd": round(self.total_usage().cost(self.config.model), 4),
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
    reviewer = Reviewer(config)
    outcomes = {case.id: CaseOutcome(case=case) for case in cases}
    jobs = [(case, i) for case in cases for i in range(repeat)]

    def run_one(job: tuple[Case, int]) -> tuple[str, ReviewResult]:
        case, _ = job
        try:
            return case.id, reviewer.review(case.submission)
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
