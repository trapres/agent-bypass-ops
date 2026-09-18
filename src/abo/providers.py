"""Provider adapters, so the same experiment can run against either vendor.

The reviewer's loop is provider-agnostic: it asks for a completion, reads
normalized tool calls off it, runs the tools, appends results, and repeats.
Everything vendor-specific — request shape, content-block format, how tool
results are threaded back, which knob controls reasoning depth — lives here.

Anthropic is the reference implementation and the default. The OpenAI adapter
exists so a run is not blocked on which key you happen to have; it is
unit-tested against a stub but, like the Anthropic path, has not been
exercised against the live API from this environment.

Cross-provider comparisons are apples-to-oranges by construction — different
tokenizers, different reasoning controls, different safety training. Compare
treatments *within* a provider, and treat the gap between providers as a
separate, weaker observation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

# Normalized stop reasons the reviewer loop understands.
END_TURN = "end_turn"
TOOL_USE = "tool_use"
REFUSAL = "refusal"
MAX_TOKENS = "max_tokens"

ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"

#: $ per 1M tokens (input, output), by provider.
PRICES: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {
        "claude-fable-5": (10.0, 50.0),
        "claude-opus-5": (5.0, 25.0),
        "claude-opus-4-8": (5.0, 25.0),
        "claude-sonnet-5": (3.0, 15.0),
        "claude-haiku-4-5": (1.0, 5.0),
    },
    "openai": {
        # Fill in from the vendor's current price list before trusting cost_usd.
        # Unknown models simply report $0.000 rather than a wrong number.
    },
}

DEFAULT_MODELS = {
    "anthropic": "claude-opus-5",
    "openai": "gpt-5",
}


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Response:
    """What the loop needs, independent of who produced it."""

    stop_reason: str
    text: str = ""
    tool_uses: list[ToolUse] = field(default_factory=list)
    model: str = ""
    usage: Any = None
    refusal_detail: str = ""
    #: Provider-native assistant turn, appended verbatim to history.
    assistant_message: Any = None


class Provider(Protocol):
    name: str

    def create(self, *, system: str, messages: list, tools: Optional[list],
               response_schema: Optional[dict], config: Any) -> Response: ...
    def user_message(self, text: str) -> Any: ...
    def tool_results(self, results: list[tuple[str, str, bool]]) -> list: ...
    def normalize_usage(self, usage: Any) -> dict: ...


def _schema_is_strict_ready(schema: dict) -> bool:
    """OpenAI strict mode requires every property to be required."""
    props = set(schema.get("properties", {}))
    required = set(schema.get("required", []))
    return props == required and schema.get("additionalProperties") is False


# -- Anthropic ----------------------------------------------------------------


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client: Any = None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client

    def create(self, *, system, messages, tools, response_schema, config) -> Response:
        params: dict[str, Any] = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            # Stable prefix: the rubric is identical across every case in a run.
            "system": [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": messages,
        }
        if tools:
            params["tools"] = tools
        # Explicit either way. Omitting it does not mean "off": on Opus 5 and
        # Fable 5 an absent `thinking` runs adaptive anyway.
        params["thinking"] = (
            {"type": "adaptive"} if config.thinking else {"type": "disabled"}
        )
        output_config: dict[str, Any] = {"effort": config.effort}
        if response_schema:
            output_config["format"] = {"type": "json_schema", "schema": response_schema}
        params["output_config"] = output_config

        if config.fallbacks:
            # Reviewing hostile diffs can trip a policy classifier; a
            # server-side fallback rescues the request inside the same call.
            raw = self.client.beta.messages.create(
                betas=[ANTHROPIC_FALLBACK_BETA], fallbacks="default", **params
            )
        else:
            raw = self.client.messages.create(**params)
        return self._normalize(raw)

    def _normalize(self, raw: Any) -> Response:
        content = list(getattr(raw, "content", []) or [])
        text = next((b.text for b in content if getattr(b, "type", "") == "text"), "")
        tool_uses = [
            ToolUse(id=b.id, name=b.name, input=b.input)
            for b in content
            if getattr(b, "type", "") == "tool_use"
        ]
        stop = getattr(raw, "stop_reason", "") or ""
        if stop == "refusal":
            normalized = REFUSAL
        elif tool_uses:
            normalized = TOOL_USE
        elif stop == "max_tokens":
            normalized = MAX_TOKENS
        else:
            normalized = END_TURN

        detail = ""
        if normalized == REFUSAL:
            d = getattr(raw, "stop_details", None)
            cat = getattr(d, "category", None) if d else None
            exp = getattr(d, "explanation", None) if d else None
            detail = f"category={cat or 'unknown'}. {exp or ''}".strip()

        return Response(
            stop_reason=normalized,
            text=text,
            tool_uses=tool_uses,
            model=getattr(raw, "model", "") or "",
            usage=getattr(raw, "usage", None),
            refusal_detail=detail,
            assistant_message={"role": "assistant", "content": content},
        )

    def user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def tool_results(self, results: list[tuple[str, str, bool]]) -> list:
        # All results go back in ONE user message — splitting them trains the
        # model out of making parallel tool calls.
        return [{
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tid,
                 "content": content, "is_error": is_error}
                for tid, content, is_error in results
            ],
        }]

    def normalize_usage(self, usage: Any) -> dict:
        return {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        }


# -- OpenAI -------------------------------------------------------------------


class OpenAIProvider:
    name = "openai"

    #: xhigh/max have no OpenAI equivalent; clamp rather than error.
    EFFORT_MAP = {"low": "low", "medium": "medium", "high": "high",
                  "xhigh": "high", "max": "high"}

    def __init__(self, client: Any = None):
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        self.client = client

    def _tools(self, tools: Optional[list]) -> Optional[list]:
        """Anthropic tool dicts -> OpenAI function tools."""
        if not tools:
            return None
        out = []
        for t in tools:
            schema = t.get("input_schema", {})
            fn: dict[str, Any] = {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": schema,
            }
            # Strict mode demands every property be required; our explore tools
            # have optional arguments, so only opt in where it actually applies.
            if t.get("strict") and _schema_is_strict_ready(schema):
                fn["strict"] = True
            out.append({"type": "function", "function": fn})
        return out

    def create(self, *, system, messages, tools, response_schema, config) -> Response:
        params: dict[str, Any] = {
            "model": config.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_completion_tokens": config.max_tokens,
        }
        converted = self._tools(tools)
        if converted:
            params["tools"] = converted
        if response_schema:
            params["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "verdict",
                    "schema": response_schema,
                    "strict": _schema_is_strict_ready(response_schema),
                },
            }
        if config.thinking:
            params["reasoning_effort"] = self.EFFORT_MAP.get(config.effort, "high")

        raw = self.client.chat.completions.create(**params)
        return self._normalize(raw)

    def _normalize(self, raw: Any) -> Response:
        choice = raw.choices[0]
        msg = choice.message
        finish = getattr(choice, "finish_reason", "") or ""

        refusal = getattr(msg, "refusal", None)
        tool_uses = []
        for tc in (getattr(msg, "tool_calls", None) or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"__unparseable__": tc.function.arguments}
            tool_uses.append(ToolUse(id=tc.id, name=tc.function.name, input=args))

        if refusal or finish == "content_filter":
            normalized = REFUSAL
        elif tool_uses:
            normalized = TOOL_USE
        elif finish == "length":
            normalized = MAX_TOKENS
        else:
            normalized = END_TURN

        return Response(
            stop_reason=normalized,
            text=getattr(msg, "content", "") or "",
            tool_uses=tool_uses,
            model=getattr(raw, "model", "") or "",
            usage=getattr(raw, "usage", None),
            refusal_detail=(refusal or "content_filter") if normalized == REFUSAL else "",
            assistant_message=msg,
        )

    def user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def tool_results(self, results: list[tuple[str, str, bool]]) -> list:
        # OpenAI wants one `tool` message per call, not one bundled message.
        return [
            {"role": "tool", "tool_call_id": tid,
             "content": f"Error: {content}" if is_error else content}
            for tid, content, is_error in results
        ]

    def normalize_usage(self, usage: Any) -> dict:
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        return {
            # Report uncached input only, matching Anthropic's accounting.
            "input_tokens": max(0, prompt - (cached or 0)),
            "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "cache_read_tokens": cached or 0,
            "cache_write_tokens": 0,  # no separate cache-write charge
        }


PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider}


def build_provider(name: str, client: Any = None) -> Provider:
    try:
        cls = PROVIDERS[name]
    except KeyError:
        raise ValueError(
            f"unknown provider {name!r}; choose from {', '.join(sorted(PROVIDERS))}"
        ) from None
    return cls(client)


def detect_provider() -> Optional[str]:
    """Pick a provider from whichever key is present in the environment."""
    import os

    anthropic_key = bool(
        os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    )
    openai_key = bool(os.environ.get("OPENAI_API_KEY"))
    if anthropic_key and not openai_key:
        return "anthropic"
    if openai_key and not anthropic_key:
        return "openai"
    if anthropic_key and openai_key:
        return "anthropic"  # deterministic tie-break; override with --provider
    return None


def credentials_present(provider: str) -> bool:
    import os

    if provider == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    try:  # an `ant auth login` profile also counts
        import anthropic

        return bool(anthropic.Anthropic().auth_headers)
    except Exception:
        return False
