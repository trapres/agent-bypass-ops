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


def _resolve_provider(args: argparse.Namespace) -> str | None:
    """Explicit --provider wins; otherwise infer from whichever key is set."""
    from .providers import detect_provider

    if getattr(args, "provider", None):
        return args.provider
    found = detect_provider()
    if found is None:
        err_console.print(
            "[red]no provider credentials found.[/red] Set ANTHROPIC_API_KEY or "
            "OPENAI_API_KEY (or run `ant auth login`), or pass --provider "
            "explicitly. Use --dry-run to inspect prompts without an API."
        )
        return None
    console.print(f"[dim]provider: {found} (auto-detected from environment)[/dim]")
    return found


def _config_from_args(args: argparse.Namespace, mode: str,
                      provider: str = "anthropic") -> ReviewConfig:
    return ReviewConfig(
        mode=mode,
        provider=provider,
        model=args.model,
        effort=args.effort,
        max_tokens=args.max_tokens,
        max_steps=args.max_steps,
        thinking=not args.no_thinking,
        fallbacks=not args.no_fallbacks,
        scanners=getattr(args, "scanners", False),
    )


def _modes(arg: str) -> list[str]:
    return ["oneshot", "agent"] if arg == "both" else [arg]


def _have_credentials(provider: str) -> bool:
    """Fail up front rather than after burning a run on every case.

    SDKs resolve credentials lazily — constructing a client succeeds with none
    set and only fails at request time.
    """
    from .providers import credentials_present

    if credentials_present(provider):
        return True
    want = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    err_console.print(
        f"[red]no {provider} credentials resolved.[/red] Set {want}"
        + ("" if provider == "openai" else " (or run `ant auth login`)")
        + ". Use --dry-run to inspect prompts without calling the API."
    )
    return False


def _add_model_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--mode", choices=["agent", "oneshot", "both"], default="agent",
                   help="agent: read-only tools over the repo. oneshot: diff in one prompt. (default: agent)")
    p.add_argument("--provider", choices=["anthropic", "openai"],
                   help="default: inferred from ANTHROPIC_API_KEY / OPENAI_API_KEY")
    p.add_argument("--model", default=None,
                   help="default: claude-opus-5 (anthropic) or gpt-5 (openai)")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], default="high")
    p.add_argument("--max-tokens", type=int, default=16_000)
    p.add_argument("--max-steps", type=int, default=12, help="agent mode turn limit (default: 12)")
    p.add_argument("--no-thinking", action="store_true", help="disable adaptive thinking")
    p.add_argument("--no-fallbacks", action="store_true",
                   help="disable the server-side refusal fallback")
    p.add_argument("--scanners", action="store_true",
                   help="give the agent run_scanner (semgrep, grype). Off by default: "
                        "the LLM-only score is the baseline. Agent mode only.")
    p.add_argument("--dry-run", action="store_true",
                   help="print the assembled prompts and exit without calling the API")


def _dry_run(submission: Submission, mode: str, scanners: bool = False) -> None:
    console.rule(f"[bold]system prompt ({mode})")
    console.print(system_prompt(mode, scanners=scanners), highlight=False)
    console.rule(f"[bold]user prompt ({mode})")
    console.print(user_prompt(submission, mode), highlight=False)
    if mode == "agent":
        console.rule("[bold]workspace")
        console.print(submission.workspace.describe())
        if scanners:
            from .scanners import installed_scanners

            console.rule("[bold]scanners")
            for name, ok in installed_scanners().items():
                console.print(f"  {'✓' if ok else '✗'} {name}")


def _warn_scanners(mode: str) -> bool:
    """Say plainly what --scanners will and won't do before spending anything."""
    from .scanners import installed_scanners

    if mode == "oneshot":
        err_console.print(
            "[red]--scanners has no effect in oneshot mode[/red] (there is no tool "
            "loop to call them from). Use --mode agent or --mode both."
        )
        return False
    status = installed_scanners()
    missing = [n for n, ok in status.items() if not ok]
    if not any(status.values()):
        err_console.print(
            f"[red]--scanners requested but none are installed[/red] "
            f"({', '.join(sorted(status))}). Install at least one, or drop the flag."
        )
        return False
    if missing:
        console.print(
            f"[yellow]not installed, will be unavailable to the agent: "
            f"{', '.join(missing)}[/yellow]"
        )
    if mode == "both":
        console.print("[dim]scanners apply to the agent run only; oneshot is unaffected.[/dim]")
    return True


def cmd_eval(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases, args.only)
    if not cases:
        err_console.print(f"[red]no cases found under {args.cases}[/red]")
        return 1

    if args.dry_run:
        for mode in _modes(args.mode):
            for case in cases:
                console.rule(f"[bold cyan]{case.id} — {case.label}")
                _dry_run(case.submission, mode, scanners=args.scanners)
        return 0

    # Config errors before credential resolution — a bad flag combination is
    # diagnosable without an API key.
    if args.scanners and not _warn_scanners(args.mode):
        return 1

    provider = _resolve_provider(args)
    if provider is None or not _have_credentials(provider):
        return 1

    exit_code = 0
    for mode in _modes(args.mode):
        config = _config_from_args(args, mode, provider)
        scan_note = ", scanners=on" if (config.scanners and mode == "agent") else ""
        console.print(
            f"[bold]Running {len(cases)} case(s) × {args.repeat} "
            f"— {config.provider}/{config.model}, mode={mode}, "
            f"effort={config.effort}{scan_note}[/bold]"
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
        suffix = "-scanners" if report.config.scanners else ""
        path = Path("runs") / f"{stamp}-{report.config.mode}{suffix}.json"
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

    if args.scanners and not args.dry_run and not _warn_scanners(args.mode):
        return 1
    provider = "anthropic"
    if not args.dry_run:
        resolved = _resolve_provider(args)
        if resolved is None or not _have_credentials(resolved):
            return 1
        provider = resolved

    for mode in _modes(args.mode):
        if args.dry_run:
            _dry_run(submission, mode, scanners=args.scanners)
            continue
        config = _config_from_args(args, mode, provider)
        console.rule(f"[bold]{submission.id} — {mode}")
        result = Reviewer(config).review(submission)
        render_review(result, config.model, config.provider)
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
