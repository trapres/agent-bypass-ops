#!/usr/bin/env python3
"""Score the scanners on their own, with no LLM involved.

This is the floor the agent has to beat, and the numbers quoted in
AgentCapabilities.md come from here. Treating "any finding" as a
merge-blocking flag, it answers: how far does pattern matching alone get you?

    python scripts/scanner_baseline.py
    python scripts/scanner_baseline.py --scanner grype
    python scripts/scanner_baseline.py --config p/github-actions --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from abo.scanners import ScannerError, available, scan  # noqa: E402
from abo.submission import load_cases  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", default=str(ROOT / "cases"))
    ap.add_argument("--scanner", default="semgrep", choices=["semgrep", "grype"])
    ap.add_argument("--config", action="append", default=None,
                    help="semgrep ruleset; repeatable (default: security-audit + secrets)")
    ap.add_argument("--all-files", action="store_true",
                    help="do not restrict findings to files the diff touched")
    ap.add_argument("--json", help="write the raw results here")
    args = ap.parse_args()

    if not available(args.scanner):
        print(f"{args.scanner} is not installed", file=sys.stderr)
        return 1

    configs = args.config or (
        ["p/security-audit", "p/secrets"] if args.scanner == "semgrep" else [""]
    )
    cases = load_cases(Path(args.cases))
    if not cases:
        print(f"no cases under {args.cases}", file=sys.stderr)
        return 1

    rows, tp = [], 0
    fp = tn = fn = 0
    print(f"{args.scanner} [{', '.join(c or 'default' for c in configs)}] "
          f"over {len(cases)} cases\n")
    print(f"{'case':<38} {'truth':<7} {'hits':<5} {'outcome'}")
    print("-" * 66)

    for case in cases:
        findings, errors = [], []
        for cfg in configs:
            try:
                r = scan(
                    case.submission.workspace,
                    scanner=args.scanner,
                    config=cfg,
                    changed_files=case.submission.files_changed,
                    only_changed=not args.all_files,
                )
                findings.extend(r.findings)
            except ScannerError as exc:
                errors.append(str(exc))

        flagged = bool(findings)
        if case.label == "unsafe":
            outcome = "TP" if flagged else "FN"
        else:
            outcome = "FP" if flagged else "TN"
        tp += outcome == "TP"; fn += outcome == "FN"
        fp += outcome == "FP"; tn += outcome == "TN"

        print(f"{case.id:<38} {case.label:<7} {len(findings):<5} {outcome}")
        for f in findings:
            print(f"      {f.rule[:46]:<48} {f.file}:{f.line} [{f.severity}]")
        for e in errors:
            print(f"      ! {e[:90]}")

        rows.append({
            "case": case.id, "label": case.label, "outcome": outcome,
            "findings": [f.to_dict() for f in findings], "errors": errors,
        })

    recall = tp / (tp + fn) if tp + fn else 0.0
    far = fp / (fp + tn) if fp + tn else 0.0
    print(f"\nTP={tp} FN={fn} TN={tn} FP={fp}")
    print(f"recall={recall:.0%}  false-alarm-rate={far:.0%}")
    print("\nScanner-only floor. Compare against `abo eval --mode agent` (LLM only) "
          "and `abo eval --mode agent --scanners` (both).")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"scanner": args.scanner, "configs": configs,
             "metrics": {"recall": recall, "false_alarm_rate": far,
                         "TP": tp, "FN": fn, "TN": tn, "FP": fp},
             "cases": rows}, indent=2))
        print(f"written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
