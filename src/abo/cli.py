"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from .harness import EvalReport, run_eval
from .prompts import system_prompt, user_prompt
from .report import console, render_eval, render_review
from .reviewer import ReviewConfig, Reviewer
from .submission import Submission, load_cases, submission_from_git

DEFAULT_CASES = Path(__file__).resolve().parents[2] / "cases"
err_console = Console(stderr=True)


def _config_from_args(args: argparse.Namespace, mode: str) -> ReviewConfig:
    return ReviewConfig(
        mode=mode,
        model=args.model,
        effort=args.effort,
        max_tokens=args.max_tokens,
        max_steps=args.max_steps,
        thinking=not args.no_thinking,
        fallbacks=not args.no_fallbacks,
    )


def _modes(arg: str) -> list[str]:
    return ["oneshot", "agent"] if arg == "both" else [arg]


def _have_credentials() -> bool:
    """Fail up front rather than after burning a run on every case.

    The SDK resolves credentials lazily — constructing a client succeeds with
    none set and only fails at request time. `auth_headers` is empty when
    nothing resolved; we check for its presence, never its value.
    """
    import anthropic

    try:
        if anthropic.Anthropic().auth_headers:
            return True
    except Exception:
        pass
    err_console.print(
        "[red]no API credentials resolved.[/red] "
        "Set ANTHROPIC_API_KEY (or run `ant auth login`). "
        "Use --dry-run to inspect prompts without calling the API."
    )
    return False


def _add_model_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--mode", choices=["agent", "oneshot", "both"], default="agent",
                   help="agent: read-only tools over the repo. oneshot: diff in one prompt. (default: agent)")
    p.add_argument("--model", default="claude-opus-5")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], default="high")
    p.add_argument("--max-tokens", type=int, default=16_000)
    p.add_argument("--max-steps", type=int, default=12, help="agent mode turn limit (default: 12)")
    p.add_argument("--no-thinking", action="store_true", help="disable adaptive thinking")
    p.add_argument("--no-fallbacks", action="store_true",
                   help="disable the server-side refusal fallback")
    p.add_argument("--dry-run", action="store_true",
                   help="print the assembled prompts and exit without calling the API")


def _dry_run(submission: Submission, mode: str) -> None:
    console.rule(f"[bold]system prompt ({mode})")
    console.print(system_prompt(mode), highlight=False)
    console.rule(f"[bold]user prompt ({mode})")
    console.print(user_prompt(submission, mode), highlight=False)
    if mode == "agent":
        console.rule("[bold]workspace")
        console.print(submission.workspace.describe())


def cmd_eval(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases, args.only)
    if not cases:
        err_console.print(f"[red]no cases found under {args.cases}[/red]")
        return 1

    if args.dry_run:
        for mode in _modes(args.mode):
            for case in cases:
                console.rule(f"[bold cyan]{case.id} — {case.label}")
                _dry_run(case.submission, mode)
        return 0

    if not _have_credentials():
        return 1

    exit_code = 0
    for mode in _modes(args.mode):
        config = _config_from_args(args, mode)
        console.print(
            f"[bold]Running {len(cases)} case(s) × {args.repeat} "
            f"— mode={mode}, model={config.model}, effort={config.effort}[/bold]"
        )
        with console.status("reviewing...") as status:
            def progress(case_id: str, verdict) -> None:
                status.update(f"reviewing... last: {case_id} -> {verdict.verdict}")

            report = run_eval(
                cases, config, repeat=args.repeat, concurrency=args.concurrency, on_done=progress
            )
        render_eval(report)
        _write_report(report, args.json)
        if report.counts()["FN"]:
            exit_code = 2  # a missed unsafe commit is the failure worth failing CI on
    return exit_code


def _write_report(report: EvalReport, explicit_path: str | None) -> None:
    if explicit_path:
        path = Path(explicit_path)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = Path("runs") / f"{stamp}-{report.config.mode}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2))
    console.print(f"[dim]report written to {path}[/dim]")


def cmd_review(args: argparse.Namespace) -> int:
    if args.diff:
        diff_path = Path(args.diff)
        submission = Submission(
            id=diff_path.name,
            diff=diff_path.read_text(),
            source=str(diff_path),
        )
    else:
        submission = submission_from_git(Path(args.repo), args.ref, args.base)

    if not submission.diff.strip():
        err_console.print("[red]empty diff — nothing to review[/red]")
        return 1

    if not args.dry_run and not _have_credentials():
        return 1

    for mode in _modes(args.mode):
        if args.dry_run:
            _dry_run(submission, mode)
            continue
        config = _config_from_args(args, mode)
        console.rule(f"[bold]{submission.id} — {mode}")
        result = Reviewer(config).review(submission)
        render_review(result, config.model)
        if args.json:
            Path(args.json).write_text(json.dumps(result.to_dict(), indent=2))
    return 0


def cmd_cases(args: argparse.Namespace) -> int:
    from rich.table import Table

    cases = load_cases(args.cases, args.only)
    table = Table(title=f"{len(cases)} cases in {args.cases}")
    table.add_column("id", overflow="fold")
    table.add_column("label")
    table.add_column("difficulty")
    table.add_column("expected categories", overflow="fold")
    table.add_column("files", justify="right")
    table.add_column("repo?", justify="center")
    for case in cases:
        has_repo = (case.path / "repo").is_dir() if case.path else False
        table.add_row(
            case.id,
            f"[red]unsafe[/red]" if case.label == "unsafe" else "[green]safe[/green]",
            case.difficulty,
            ", ".join(case.categories) or "-",
            str(len(case.submission.files_changed)),
            "✓" if has_repo else "-",
        )
    console.print(table)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="abo",
        description="Evaluate how well an LLM agent judges whether a code submission is safe.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("eval", help="run the labeled corpus and score the reviewer")
    p_eval.add_argument("--cases", default=str(DEFAULT_CASES), help="directory of labeled cases")
    p_eval.add_argument("--only", nargs="*", help="run only these case ids")
    p_eval.add_argument("--repeat", type=int, default=1, help="runs per case, for stability")
    p_eval.add_argument("--concurrency", type=int, default=4)
    p_eval.add_argument("--json", help="write the report here instead of runs/")
    _add_model_args(p_eval)
    p_eval.set_defaults(func=cmd_eval)

    p_review = sub.add_parser("review", help="review one unlabeled commit or diff file")
    src = p_review.add_mutually_exclusive_group(required=True)
    src.add_argument("--repo", help="path to a git repository")
    src.add_argument("--diff", help="path to a .diff/.patch file")
    p_review.add_argument("--ref", default="HEAD", help="commit to review (default: HEAD)")
    p_review.add_argument("--base", help="review base...ref instead of a single commit")
    p_review.add_argument("--json", help="write the result here")
    _add_model_args(p_review)
    p_review.set_defaults(func=cmd_review)

    p_cases = sub.add_parser("cases", help="list the labeled corpus")
    p_cases.add_argument("--cases", default=str(DEFAULT_CASES))
    p_cases.add_argument("--only", nargs="*")
    p_cases.set_defaults(func=cmd_cases)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        err_console.print(f"[red]{type(exc).__name__}: {exc}[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
