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

import anthropic
from pydantic import ValidationError

from .models import VERDICT_SCHEMA, Verdict
from .prompts import system_prompt, user_prompt
from .submission import Submission
from .workspace import WorkspaceError

MAX_TOOL_RESULT_CHARS = 20_000

# $ per 1M tokens (input, output). Cache reads bill at 0.1x input, writes at 1.25x.
PRICES = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class ReviewConfig:
    mode: str = "agent"  # "agent" | "oneshot"
    model: str = "claude-opus-5"
    effort: str = "high"  # low | medium | high | xhigh | max
    max_tokens: int = 16_000
    max_steps: int = 12  # agent mode only
    thinking: bool = True
    fallbacks: bool = True  # server-side fallback on a policy refusal


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, u: Any) -> None:
        self.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.output_tokens += getattr(u, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(u, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(u, "cache_creation_input_tokens", 0) or 0

    def cost(self, model: str) -> float:
        in_price, out_price = PRICES.get(model, (0.0, 0.0))
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

AGENT_TOOLS = EXPLORE_TOOLS + [SUBMIT_VERDICT_TOOL]


def _abstain(summary: str) -> Verdict:
    return Verdict(verdict="needs_human_review", confidence=0.0, summary=summary, findings=[])


def _refusal_summary(response: Any) -> str:
    details = getattr(response, "stop_details", None)
    category = getattr(details, "category", None) if details else None
    explanation = getattr(details, "explanation", None) if details else None
    return f"Model declined to answer (category={category or 'unknown'}). {explanation or ''}".strip()


class Reviewer:
    def __init__(self, config: ReviewConfig, client: Optional[anthropic.Anthropic] = None):
        self.config = config
        self.client = client or anthropic.Anthropic()

    # -- transport ---------------------------------------------------------

    def _create(self, **kwargs: Any) -> Any:
        cfg = self.config
        # Stable prefix first (tools, then system) so the cached block covers
        # everything that does not vary between submissions.
        params: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            **kwargs,
        }
        # Explicit either way. Omitting the parameter does not mean "off": on
        # Opus 5 and Fable 5 it runs adaptive anyway, so --no-thinking would
        # silently do nothing.
        params["thinking"] = {"type": "adaptive"} if cfg.thinking else {"type": "disabled"}
        output_config = params.setdefault("output_config", {})
        output_config["effort"] = cfg.effort

        if cfg.fallbacks:
            # A reviewer reading hostile diffs can trip a policy classifier; a
            # server-side fallback rescues the request inside the same call.
            return self.client.beta.messages.create(
                betas=[FALLBACK_BETA], fallbacks="default", **params
            )
        return self.client.messages.create(**params)

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
            system=[
                {
                    "type": "text",
                    "text": system_prompt("oneshot"),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt(submission, "oneshot")}],
            output_config={"format": {"type": "json_schema", "schema": VERDICT_SCHEMA}},
        )
        result.usage.add(response.usage)
        result.steps = 1
        result.served_by = getattr(response, "model", "") or ""

        if response.stop_reason == "refusal":
            result.verdict = _abstain(_refusal_summary(response))
            result.error = "refusal"
            return result

        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            result.verdict = Verdict.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            result.verdict = _abstain(f"could not parse verdict: {exc}")
            result.error = f"parse_error: {exc}"
        return result

    def _review_agent(self, submission: Submission) -> ReviewResult:
        cfg = self.config
        result = ReviewResult(submission_id=submission.id, verdict=_abstain("not run"))
        system = [
            {
                "type": "text",
                "text": system_prompt("agent"),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_prompt(submission, "agent")}
        ]
        nudged = False

        for step in range(cfg.max_steps):
            response = self._create(system=system, messages=messages, tools=AGENT_TOOLS)
            result.usage.add(response.usage)
            result.steps = step + 1
            result.served_by = getattr(response, "model", "") or ""

            if response.stop_reason == "refusal":
                result.verdict = _abstain(_refusal_summary(response))
                result.error = "refusal"
                return result

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                if nudged:
                    text = next((b.text for b in response.content if b.type == "text"), "")
                    result.verdict = _abstain("model ended its turn without calling submit_verdict")
                    result.error = f"no_verdict_tool_call: {text[:400]}"
                    return result
                nudged = True
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": "Call submit_verdict now with your decision.",
                    }
                )
                continue

            messages.append({"role": "assistant", "content": response.content})

            verdict_block = next((b for b in tool_uses if b.name == "submit_verdict"), None)
            if verdict_block is not None:
                result.tool_calls.append("submit_verdict")
                try:
                    result.verdict = Verdict.model_validate(verdict_block.input)
                except ValidationError as exc:
                    result.verdict = _abstain(f"invalid verdict payload: {exc}")
                    result.error = f"validation_error: {exc}"
                return result

            tool_results = []
            for block in tool_uses:
                result.tool_calls.append(f"{block.name}({_brief(block.input)})")
                content, is_error = self._run_tool(submission, block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content[:MAX_TOOL_RESULT_CHARS],
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        result.verdict = _abstain(f"reviewer did not conclude within {cfg.max_steps} steps")
        result.error = "step_limit"
        return result

    # -- tool dispatch -----------------------------------------------------

    def _run_tool(self, submission: Submission, name: str, args: dict[str, Any]) -> tuple[str, bool]:
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
            return (f"unknown tool: {name}", True)
        except WorkspaceError as exc:
            return (f"Error: {exc}", True)
        except KeyError as exc:
            return (f"Error: missing required argument {exc}", True)
        except Exception as exc:  # a tool failure must not kill the review
            return (f"Error: {type(exc).__name__}: {exc}", True)


def _brief(args: dict[str, Any]) -> str:
    return ", ".join(f"{k}={str(v)[:60]}" for k, v in args.items())
