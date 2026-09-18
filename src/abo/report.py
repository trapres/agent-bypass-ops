"""Console rendering for eval runs and single reviews."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .harness import EvalReport
from .models import Verdict
from .reviewer import ReviewResult

OUTCOME_STYLE = {"TP": "green", "TN": "green", "FP": "yellow", "FN": "red"}
VERDICT_STYLE = {"safe": "green", "unsafe": "red", "needs_human_review": "yellow"}

console = Console()


def _verdict_text(verdict: str) -> Text:
    return Text(verdict, style=VERDICT_STYLE.get(verdict, "white"))


def render_eval(report: EvalReport) -> None:
    table = Table(title=f"Case results — mode={report.config.mode} model={report.config.model}")
    table.add_column("case", overflow="fold")
    table.add_column("truth")
    table.add_column("verdict")
    table.add_column("", justify="center")  # outcome
    table.add_column("conf", justify="right")
    table.add_column("findings", justify="right")
    table.add_column("cat", justify="center")
    table.add_column("steps", justify="right")
    table.add_column("sec", justify="right")

    for outcome in report.outcomes:
        for i, result in enumerate(outcome.results):
            code = outcome.classify(result)
            hit = outcome.found_expected_category(result)
            table.add_row(
                outcome.case.id if i == 0 else "",
                outcome.case.label if i == 0 else "",
                _verdict_text(result.verdict.verdict),
                Text(code, style=OUTCOME_STYLE[code]),
                f"{result.verdict.confidence:.2f}",
                str(len(result.verdict.findings)),
                "-" if hit is None else ("✓" if hit else "✗"),
                str(result.steps),
                f"{result.duration_s:.1f}",
            )
    console.print(table)

    m = report.metrics()
    c = report.counts()
    usage = report.total_usage()
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column()
    summary.add_row("runs", f"{int(m['runs'])}")
    summary.add_row("accuracy", f"{m['accuracy']:.1%}")
    summary.add_row("recall (caught unsafe)", f"{m['recall']:.1%}  [{c['TP']} of {c['TP'] + c['FN']}]")
    summary.add_row("precision", f"{m['precision']:.1%}")
    summary.add_row("false alarms on safe", f"{m['false_alarm_rate']:.1%}  [{c['FP']} of {c['FP'] + c['TN']}]")
    summary.add_row("F1", f"{m['f1']:.2f}")
    summary.add_row("abstained", f"{m['abstain_rate']:.1%}  [{c['abstain']}]")
    summary.add_row("verdict stability", f"{m['stability']:.1%}")
    if c["error"]:
        summary.add_row("errors", Text(str(c["error"]), style="red"))
    summary.add_row(
        "tokens",
        f"in {usage.input_tokens:,} / out {usage.output_tokens:,} / cached {usage.cache_read_tokens:,}",
    )
    summary.add_row("cost", f"${usage.cost(report.config.model):.3f}")
    console.print(Panel(summary, title="Summary", expand=False))

    misses = [
        (o, r)
        for o in report.outcomes
        for r in o.results
        if o.classify(r) in ("FP", "FN")
    ]
    if misses:
        console.print("\n[bold]Misses[/bold]")
        for outcome, result in misses:
            code = outcome.classify(result)
            console.print(
                f"  [{OUTCOME_STYLE[code]}]{code}[/] {outcome.case.id} "
                f"(truth={outcome.case.label}, said={result.verdict.verdict}): "
                f"{result.verdict.summary}"
            )
            if outcome.case.notes:
                console.print(f"      [dim]case note: {outcome.case.notes}[/dim]")


def render_review(result: ReviewResult, config_model: str) -> None:
    v: Verdict = result.verdict
    header = Text.assemble(
        (v.verdict.upper(), VERDICT_STYLE.get(v.verdict, "white")),
        f"  confidence {v.confidence:.2f}",
    )
    console.print(Panel(Text(v.summary), title=header, expand=False))

    if v.findings:
        table = Table(show_header=True)
        table.add_column("severity")
        table.add_column("category")
        table.add_column("location", overflow="fold")
        table.add_column("issue", overflow="fold")
        for f in v.findings:
            style = "red" if f.severity in ("high", "critical") else "yellow" if f.severity == "medium" else "dim"
            table.add_row(Text(f.severity, style=style), f.category, f.location(), f.description)
        console.print(table)
    else:
        console.print("[dim]No findings reported.[/dim]")

    if result.scans:
        console.print("\n[bold]Scanners run[/bold]")
        for s in result.scans:
            if s.error:
                console.print(f"  [red]{s.scanner} ({s.config}): {s.error}[/red]")
                continue
            note = ""
            if s.dropped_unchanged:
                note = f", {s.dropped_unchanged} dropped as pre-existing"
            console.print(
                f"  {s.scanner} [dim]({s.config})[/dim]: "
                f"{len(s.findings)} finding(s){note} in {s.duration_s:.1f}s"
            )
            for f in s.findings[:5]:
                console.print(f"      [dim]{f.severity} {f.rule} — {f.file}:{f.line}[/dim]")

    if result.tool_calls:
        console.print(f"\n[dim]{len(result.tool_calls)} tool calls over {result.steps} steps:[/dim]")
        for call in result.tool_calls:
            console.print(f"  [dim]- {call}[/dim]")

    console.print(
        f"\n[dim]{result.usage.input_tokens:,} in / {result.usage.output_tokens:,} out / "
        f"{result.usage.cache_read_tokens:,} cached · "
        f"${result.usage.cost(config_model):.4f} · {result.duration_s:.1f}s[/dim]"
    )
    if result.error:
        console.print(f"[red]error: {result.error}[/red]")
