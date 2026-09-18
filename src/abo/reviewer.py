"""The reviewer itself: one interface, two levels of agency.

``oneshot`` sends the diff and takes a structured verdict back in a single
request. ``agent`` gives the model read-only tools over the project and lets it
decide when it has seen enough. Both return the same ``Verdict``, so an eval
run can attribute any score difference to the agency and not to the schema.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import ValidationError

from .models import VERDICT_SCHEMA, Verdict
from .prompts import system_prompt, user_prompt
from .providers import DEFAULT_MODELS, PRICES, REFUSAL, Response, build_provider
from .scanners import SCANNER_HELP, SEMGREP_RULESETS, ScannerError, scan
from .submission import Submission
from .workspace import WorkspaceError

MAX_TOOL_RESULT_CHARS = 20_000


@dataclass
class ReviewConfig:
    mode: str = "agent"  # "agent" | "oneshot"
    provider: str = "anthropic"  # "anthropic" | "openai"
    model: str = ""  # empty -> the provider's default
    effort: str = "high"  # low | medium | high | xhigh | max
    max_tokens: int = 16_000
    max_steps: int = 12  # agent mode only
    thinking: bool = True
    fallbacks: bool = True  # server-side fallback on a policy refusal
    # Off by default: the LLM-only score is the baseline everything else is
    # measured against, so it must be the thing you get when you ask for nothing.
    scanners: bool = False
    scan_only_changed: bool = True

    def __post_init__(self) -> None:
        # `--provider openai` alone should work without also demanding a model
        # the other vendor has never heard of.
        if not self.model:
            self.model = DEFAULT_MODELS[self.provider]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, u: Any) -> None:
        """Accept a raw Anthropic usage object (kept for direct callers)."""
        self.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.output_tokens += getattr(u, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(u, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(u, "cache_creation_input_tokens", 0) or 0

    def add_normalized(self, d: dict) -> None:
        """Accept the provider-normalized dict."""
        self.input_tokens += d.get("input_tokens", 0)
        self.output_tokens += d.get("output_tokens", 0)
        self.cache_read_tokens += d.get("cache_read_tokens", 0)
        self.cache_write_tokens += d.get("cache_write_tokens", 0)

    def cost(self, model: str, provider: str = "anthropic") -> float:
        in_price, out_price = PRICES.get(provider, {}).get(model, (0.0, 0.0))
        return (
            self.input_tokens * in_price
            + self.cache_read_tokens * in_price * 0.1
            + self.cache_write_tokens * in_price * 1.25
            + self.output_tokens * out_price
        ) / 1_000_000

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


@dataclass
class ReviewResult:
    submission_id: str
    verdict: Verdict
    usage: Usage = field(default_factory=Usage)
    steps: int = 0
    tool_calls: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    error: Optional[str] = None
    served_by: str = ""
    scans: list = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "verdict": self.verdict.model_dump(),
            "usage": self.usage.to_dict(),
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "duration_s": round(self.duration_s, 2),
            "error": self.error,
            "served_by": self.served_by,
            # Kept so you can ask whether a finding came from the scanner or the
            # model, and whether the model confirmed or ignored a scanner hit.
            "scans": [s.to_dict() for s in self.scans],
        }


SUBMIT_VERDICT_TOOL: dict[str, Any] = {
    "name": "submit_verdict",
    "description": (
        "Submit your final security verdict for the submission under review. "
        "Call this exactly once, after you have gathered the context you need. "
        "This ends the review."
    ),
    "strict": True,
    "input_schema": VERDICT_SCHEMA,
}

EXPLORE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_files",
        "description": (
            "List files in the project as it stands after this change. "
            "Read-only. Returns paths relative to the project root."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to list, relative to the project root. Defaults to the root.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a file from the project as it stands after this change, with line numbers. "
            "Read-only; the file is never executed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to the project root."},
                "start_line": {"type": "integer", "description": "1-indexed first line to return. Defaults to 1."},
                "max_lines": {"type": "integer", "description": "How many lines to return. Defaults to 400."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "grep",
        "description": (
            "Search the project's files with a regular expression. "
            "Returns up to 60 matches as path:line:text. Use this to find callers, "
            "definitions, and other uses of a symbol before concluding."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regular expression."},
                "path_glob": {
                    "type": "string",
                    "description": "Optional glob to restrict the search, e.g. '*.py' or 'src/*'.",
                },
            },
            "required": ["pattern"],
        },
    },
]

#: Opt-in. The model picks the scanner *and* the ruleset, because ruleset
#: choice drives recall more than scanner choice does — p/security-audit misses
#: the pull_request_target case that p/github-actions catches at ERROR.
RUN_SCANNER_TOOL: dict[str, Any] = {
    "name": "run_scanner",
    "description": (
        "Run an open-source static analyzer over the project and return its findings. "
        "The analyzer reads the code; it never executes it.\n\n"
        + "\n".join(f"- {name}: {help_}" for name, help_ in SCANNER_HELP.items())
        + "\n\nScanner output is evidence, not a verdict. A hit may be a false "
        "positive — confirm it by reading the code before you report it, and cite "
        "the code rather than the scanner. No findings is weak evidence of safety: "
        "these tools match patterns and are blind to logic flaws such as a "
        "permission check placed in the wrong order.\n\n"
        "By default, findings in files this submission did not touch are dropped "
        "as pre-existing; the result says how many."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "scanner": {
                "type": "string",
                "enum": sorted(SCANNER_HELP),
                "description": "Which analyzer to run.",
            },
            "config": {
                "type": "string",
                "description": (
                    "For semgrep, the ruleset. Pick the one that matches what the "
                    "diff touched — this choice matters more than any other:\n"
                    + "\n".join(f"  {k}: {v}" for k, v in SEMGREP_RULESETS.items())
                    + "\nIgnored by grype."
                ),
            },
            "include_unchanged_files": {
                "type": "boolean",
                "description": (
                    "Defaults to false. Set true only to inspect the project's "
                    "pre-existing state; findings in untouched files are not this "
                    "submission's doing."
                ),
            },
        },
        "required": ["scanner"],
    },
}

AGENT_TOOLS = EXPLORE_TOOLS + [SUBMIT_VERDICT_TOOL]
AGENT_TOOLS_WITH_SCANNERS = EXPLORE_TOOLS + [RUN_SCANNER_TOOL, SUBMIT_VERDICT_TOOL]


def _abstain(summary: str) -> Verdict:
    return Verdict(verdict="needs_human_review", confidence=0.0, summary=summary, findings=[])


def _refusal_summary(response: Any) -> str:
    details = getattr(response, "stop_details", None)
    category = getattr(details, "category", None) if details else None
    explanation = getattr(details, "explanation", None) if details else None
    return f"Model declined to answer (category={category or 'unknown'}). {explanation or ''}".strip()


class Reviewer:
    def __init__(self, config: ReviewConfig, client: Any = None):
        self.config = config
        self.provider = build_provider(config.provider, client)
        # Kept for tests and callers that reach for the underlying SDK client.
        self.client = getattr(self.provider, "client", client)

    # -- transport ---------------------------------------------------------

    def _create(self, **kwargs: Any) -> Any:
        return self.provider.create(config=self.config, **kwargs)

    # -- public API --------------------------------------------------------

    def review(self, submission: Submission) -> ReviewResult:
        started = time.monotonic()
        if self.config.mode == "oneshot":
            result = self._review_oneshot(submission)
        elif self.config.mode == "agent":
            result = self._review_agent(submission)
        else:
            raise ValueError(f"unknown mode: {self.config.mode}")
        result.duration_s = time.monotonic() - started
        return result

    # -- modes -------------------------------------------------------------

    def _review_oneshot(self, submission: Submission) -> ReviewResult:
        result = ReviewResult(submission_id=submission.id, verdict=_abstain("not run"))
        response = self._create(
            system=system_prompt("oneshot"),
            messages=[self.provider.user_message(user_prompt(submission, "oneshot"))],
            tools=None,
            response_schema=VERDICT_SCHEMA,
        )
        self._record(result, response)
        result.steps = 1

        if response.stop_reason == REFUSAL:
            result.verdict = _abstain(f"Model declined to answer. {response.refusal_detail}")
            result.error = "refusal"
            return result

        try:
            result.verdict = Verdict.model_validate(json.loads(response.text))
        except (json.JSONDecodeError, ValidationError) as exc:
            result.verdict = _abstain(f"could not parse verdict: {exc}")
            result.error = f"parse_error: {exc}"
        return result

    def _record(self, result: ReviewResult, response: Response) -> None:
        result.usage.add_normalized(self.provider.normalize_usage(response.usage))
        result.served_by = response.model

    def _review_agent(self, submission: Submission) -> ReviewResult:
        cfg = self.config
        result = ReviewResult(submission_id=submission.id, verdict=_abstain("not run"))
        system = system_prompt("agent", scanners=cfg.scanners)
        messages: list[Any] = [
            self.provider.user_message(user_prompt(submission, "agent"))
        ]
        nudged = False

        tools = AGENT_TOOLS_WITH_SCANNERS if cfg.scanners else AGENT_TOOLS

        for step in range(cfg.max_steps):
            response = self._create(
                system=system, messages=messages, tools=tools, response_schema=None
            )
            self._record(result, response)
            result.steps = step + 1

            if response.stop_reason == REFUSAL:
                result.verdict = _abstain(
                    f"Model declined to answer. {response.refusal_detail}"
                )
                result.error = "refusal"
                return result

            if not response.tool_uses:
                if nudged:
                    result.verdict = _abstain(
                        "model ended its turn without calling submit_verdict"
                    )
                    result.error = f"no_verdict_tool_call: {response.text[:400]}"
                    return result
                nudged = True
                messages.append(response.assistant_message)
                messages.append(
                    self.provider.user_message(
                        "Call submit_verdict now with your decision."
                    )
                )
                continue

            messages.append(response.assistant_message)

            verdict_call = next(
                (t for t in response.tool_uses if t.name == "submit_verdict"), None
            )
            if verdict_call is not None:
                result.tool_calls.append("submit_verdict")
                try:
                    result.verdict = Verdict.model_validate(verdict_call.input)
                except ValidationError as exc:
                    result.verdict = _abstain(f"invalid verdict payload: {exc}")
                    result.error = f"validation_error: {exc}"
                return result

            tool_results = []
            for call in response.tool_uses:
                result.tool_calls.append(f"{call.name}({_brief(call.input)})")
                content, is_error = self._run_tool(
                    submission, call.name, call.input, collect=result.scans
                )
                tool_results.append(
                    (call.id, content[:MAX_TOOL_RESULT_CHARS], is_error)
                )
            messages.extend(self.provider.tool_results(tool_results))

        result.verdict = _abstain(f"reviewer did not conclude within {cfg.max_steps} steps")
        result.error = "step_limit"
        return result

    # -- tool dispatch -----------------------------------------------------

    def _run_tool(
        self,
        submission: Submission,
        name: str,
        args: dict[str, Any],
        collect: Optional[list] = None,
    ) -> tuple[str, bool]:
        # `collect` is the calling review's scan list. Reviewer instances are
        # shared across threads by run_eval, so nothing per-review lives on self.
        ws = submission.workspace
        try:
            if name == "list_files":
                files = ws.list_files(args.get("path", "."))
                return ("\n".join(files) or "(empty)", False)
            if name == "read_file":
                return (
                    ws.read_file(
                        args["path"],
                        int(args.get("start_line", 1) or 1),
                        int(args.get("max_lines", 400) or 400),
                    ),
                    False,
                )
            if name == "grep":
                hits = ws.grep(args["pattern"], args.get("path_glob", "") or "")
                return ("\n".join(hits) or "(no matches)", False)
            if name == "run_scanner":
                only_changed = not bool(args.get("include_unchanged_files", False))
                scan_result = scan(
                    ws,
                    scanner=args["scanner"],
                    config=args.get("config", "") or "",
                    changed_files=submission.files_changed,
                    only_changed=only_changed and self.config.scan_only_changed,
                )
                if collect is not None:
                    collect.append(scan_result)
                return (scan_result.render(), False)
            return (f"unknown tool: {name}", True)
        except ScannerError as exc:
            # A missing or failing scanner degrades the review; it never ends it.
            return (f"Error: {exc}", True)
        except WorkspaceError as exc:
            return (f"Error: {exc}", True)
        except KeyError as exc:
            return (f"Error: missing required argument {exc}", True)
        except Exception as exc:  # a tool failure must not kill the review
            return (f"Error: {type(exc).__name__}: {exc}", True)


def _brief(args: dict[str, Any]) -> str:
    return ", ".join(f"{k}={str(v)[:60]}" for k, v in args.items())
