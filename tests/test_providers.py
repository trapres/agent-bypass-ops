"""Provider adapter tests, against stubs. No network, no keys.

The OpenAI adapter has never been exercised against the live API from this
environment; these tests pin the request shape and the response normalization,
which is what would break first if the mapping is wrong.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from abo.models import VERDICT_SCHEMA
from abo.providers import (
    END_TURN,
    MAX_TOKENS,
    REFUSAL,
    TOOL_USE,
    AnthropicProvider,
    OpenAIProvider,
    build_provider,
    detect_provider,
    credentials_present,
)
from abo.reviewer import AGENT_TOOLS, ReviewConfig, Reviewer, Usage
from abo.submission import Submission
from abo.workspace import DirWorkspace

VERDICT = {
    "verdict": "unsafe", "confidence": 0.9, "summary": "bad",
    "findings": [{"file": "a.py", "line": 1, "severity": "high",
                  "category": "auth-bypass", "description": "d", "evidence": "e"}],
}


# -- OpenAI stubs --------------------------------------------------------------


def oa_response(content=None, tool_calls=None, finish="stop", refusal=None,
                cached=0) -> SimpleNamespace:
    msg = SimpleNamespace(content=content, refusal=refusal, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg, finish_reason=finish)],
        model="gpt-5",
        usage=SimpleNamespace(
            prompt_tokens=1000, completion_tokens=200,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
        ),
    )


def oa_tool_call(name: str, args: dict, id_="call_1") -> SimpleNamespace:
    return SimpleNamespace(
        id=id_, function=SimpleNamespace(name=name, arguments=json.dumps(args))
    )


class FakeOpenAI:
    def __init__(self, queue):
        self.queue = list(queue)
        self.calls: list[dict] = []
        outer = self

        def create(**kw):
            outer.calls.append({**kw, "messages": list(kw.get("messages", []))})
            if not outer.queue:
                raise AssertionError("more calls than queued")
            return outer.queue.pop(0)

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


@pytest.fixture
def submission(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    return Submission(id="s", diff="+++ b/a.py\n+x = 1\n",
                      workspace=DirWorkspace(tmp_path))


# -- request shape -------------------------------------------------------------


def test_openai_translates_anthropic_tools_to_function_tools(submission):
    client = FakeOpenAI([oa_response(tool_calls=[oa_tool_call("submit_verdict", VERDICT)])])
    Reviewer(ReviewConfig(mode="agent", provider="openai"), client).review(submission)

    tools = client.calls[0]["tools"]
    assert {t["type"] for t in tools} == {"function"}
    assert [t["function"]["name"] for t in tools] == [t["name"] for t in AGENT_TOOLS]
    assert tools[0]["function"]["parameters"] == AGENT_TOOLS[0]["input_schema"]


def test_openai_only_marks_strict_where_the_schema_qualifies(submission):
    client = FakeOpenAI([oa_response(tool_calls=[oa_tool_call("submit_verdict", VERDICT)])])
    Reviewer(ReviewConfig(mode="agent", provider="openai"), client).review(submission)

    by_name = {t["function"]["name"]: t["function"] for t in client.calls[0]["tools"]}
    # every property required + additionalProperties:false
    assert by_name["submit_verdict"].get("strict") is True
    # read_file has optional args, so strict would be rejected by the API
    assert "strict" not in by_name["read_file"]


def test_openai_puts_the_system_prompt_in_the_message_list(submission):
    client = FakeOpenAI([oa_response(content=json.dumps(VERDICT))])
    Reviewer(ReviewConfig(mode="oneshot", provider="openai"), client).review(submission)

    messages = client.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "security reviewer" in messages[0]["content"].lower()
    assert messages[1]["role"] == "user"
    assert "max_completion_tokens" in client.calls[0]
    assert "max_tokens" not in client.calls[0]


def test_openai_oneshot_requests_a_json_schema_response(submission):
    client = FakeOpenAI([oa_response(content=json.dumps(VERDICT))])
    Reviewer(ReviewConfig(mode="oneshot", provider="openai"), client).review(submission)

    fmt = client.calls[0]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["schema"] is VERDICT_SCHEMA
    assert fmt["json_schema"]["strict"] is True


@pytest.mark.parametrize("effort,expected", [
    ("low", "low"), ("medium", "medium"), ("high", "high"),
    ("xhigh", "high"), ("max", "high"),   # no OpenAI equivalent; clamped
])
def test_openai_maps_effort_to_reasoning_effort(submission, effort, expected):
    client = FakeOpenAI([oa_response(content=json.dumps(VERDICT))])
    Reviewer(ReviewConfig(mode="oneshot", provider="openai", effort=effort),
             client).review(submission)
    assert client.calls[0]["reasoning_effort"] == expected


def test_openai_omits_reasoning_effort_when_thinking_is_off(submission):
    client = FakeOpenAI([oa_response(content=json.dumps(VERDICT))])
    Reviewer(ReviewConfig(mode="oneshot", provider="openai", thinking=False),
             client).review(submission)
    assert "reasoning_effort" not in client.calls[0]


# -- response normalization ----------------------------------------------------


def test_openai_oneshot_parses_a_verdict(submission):
    client = FakeOpenAI([oa_response(content=json.dumps(VERDICT))])
    r = Reviewer(ReviewConfig(mode="oneshot", provider="openai"), client).review(submission)
    assert r.verdict.verdict == "unsafe"
    assert r.error is None
    assert r.served_by == "gpt-5"


def test_openai_agent_loop_runs_tools_then_submits(submission):
    client = FakeOpenAI([
        oa_response(tool_calls=[oa_tool_call("list_files", {}, "c1")], finish="tool_calls"),
        oa_response(tool_calls=[oa_tool_call("submit_verdict", VERDICT, "c2")],
                    finish="tool_calls"),
    ])
    r = Reviewer(ReviewConfig(mode="agent", provider="openai"), client).review(submission)

    assert r.verdict.verdict == "unsafe"
    assert r.steps == 2
    # tool results go back as one `tool` message per call, keyed by id
    second = client.calls[1]["messages"]
    assert second[-1]["role"] == "tool"
    assert second[-1]["tool_call_id"] == "c1"


def test_openai_refusal_becomes_an_abstention(submission):
    client = FakeOpenAI([oa_response(refusal="I can't help with that")])
    r = Reviewer(ReviewConfig(mode="oneshot", provider="openai"), client).review(submission)
    assert r.verdict.verdict == "needs_human_review"
    assert r.error == "refusal"


def test_openai_content_filter_is_also_a_refusal(submission):
    client = FakeOpenAI([oa_response(content=None, finish="content_filter")])
    r = Reviewer(ReviewConfig(mode="oneshot", provider="openai"), client).review(submission)
    assert r.error == "refusal"


def test_openai_unparseable_tool_arguments_do_not_crash(submission):
    bad = SimpleNamespace(id="c1", function=SimpleNamespace(
        name="submit_verdict", arguments="{not json"))
    client = FakeOpenAI([oa_response(tool_calls=[bad], finish="tool_calls")])
    r = Reviewer(ReviewConfig(mode="agent", provider="openai"), client).review(submission)
    assert r.verdict.verdict == "needs_human_review"
    assert r.error.startswith("validation_error")


def test_openai_usage_reports_uncached_input_like_anthropic(submission):
    client = FakeOpenAI([oa_response(content=json.dumps(VERDICT), cached=800)])
    r = Reviewer(ReviewConfig(mode="oneshot", provider="openai"), client).review(submission)
    assert r.usage.input_tokens == 200     # 1000 prompt - 800 cached
    assert r.usage.cache_read_tokens == 800
    assert r.usage.output_tokens == 200


# -- config / selection --------------------------------------------------------


def test_choosing_openai_swaps_the_default_model():
    assert ReviewConfig(provider="openai").model == "gpt-5"
    assert ReviewConfig(provider="anthropic").model == "claude-opus-5"
    # an explicit model is never overridden
    assert ReviewConfig(provider="openai", model="o4-mini").model == "o4-mini"


def test_cost_is_scoped_per_provider():
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert u.cost("claude-opus-5", "anthropic") == pytest.approx(30.0)
    # unknown/unpriced model reports 0 rather than an invented number
    assert u.cost("gpt-5", "openai") == 0.0


def test_build_provider_rejects_unknown_names():
    with pytest.raises(ValueError, match="unknown provider"):
        build_provider("bedrock-ish")


@pytest.mark.parametrize("env,expected", [
    ({"ANTHROPIC_API_KEY": "x"}, "anthropic"),
    ({"OPENAI_API_KEY": "x"}, "openai"),
    ({"ANTHROPIC_API_KEY": "x", "OPENAI_API_KEY": "y"}, "anthropic"),  # tie-break
    ({}, None),
])
def test_detect_provider_reads_the_environment(monkeypatch, env, expected):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert detect_provider() == expected


def test_credentials_present_for_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert credentials_present("openai") is False
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert credentials_present("openai") is True


# -- the two providers stay interchangeable ------------------------------------


def test_both_providers_produce_the_same_verdict_type(submission):
    anth = Reviewer(ReviewConfig(mode="oneshot", provider="anthropic"),
                    _FakeAnthropic(json.dumps(VERDICT))).review(submission)
    oai = Reviewer(ReviewConfig(mode="oneshot", provider="openai"),
                   FakeOpenAI([oa_response(content=json.dumps(VERDICT))])).review(submission)
    assert type(anth.verdict) is type(oai.verdict)
    assert anth.verdict.model_dump() == oai.verdict.model_dump()


class _FakeAnthropic:
    """Minimal Anthropic stub for the interchangeability check."""

    def __init__(self, text):
        resp = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn", model="claude-opus-5",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                  cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0),
        )
        self.messages = SimpleNamespace(create=lambda **kw: resp)
        self.beta = SimpleNamespace(
            messages=SimpleNamespace(create=lambda **kw: resp))
