"""Reviewer tests against a stubbed API client — no network, no credentials."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from abo.models import VERDICT_SCHEMA
from abo.reviewer import AGENT_TOOLS, ReviewConfig, Reviewer, Usage
from abo.submission import Submission
from abo.workspace import DirWorkspace

VERDICT_JSON = {
    "verdict": "unsafe",
    "confidence": 0.88,
    "summary": "Exfiltrates the environment.",
    "findings": [
        {
            "file": "scripts/check-env.js",
            "line": 12,
            "severity": "critical",
            "category": "credential-exfiltration",
            "description": "POSTs process.env to a third-party host.",
            "evidence": "env: process.env",
        }
    ],
}


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_block(name: str, inp: dict, id_: str = "tu_1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id_)


def response(content, stop_reason="end_turn", **extra) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        model="claude-opus-5",
        usage=SimpleNamespace(
            input_tokens=100, output_tokens=50,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        ),
        **extra,
    )


@dataclass
class FakeClient:
    """Returns queued responses and records the params it was called with."""

    queue: list = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    def _create(self, **params: Any):
        # Snapshot `messages`: the reviewer keeps appending to the same list,
        # so recording it by reference would show every call the final state.
        self.calls.append({**params, "messages": list(params.get("messages", []))})
        if not self.queue:
            raise AssertionError("reviewer made more API calls than the test queued")
        return self.queue.pop(0)

    def __post_init__(self):
        outer = self
        self.messages = SimpleNamespace(create=lambda **kw: outer._create(**kw))
        self.beta = SimpleNamespace(
            messages=SimpleNamespace(
                create=lambda betas=None, fallbacks=None, **kw: outer._create(
                    betas=betas, fallbacks=fallbacks, **kw
                )
            )
        )


@pytest.fixture
def submission(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check-env.js").write_text("const env = process.env;\n")
    return Submission(
        id="fixture",
        diff="diff --git a/scripts/check-env.js b/scripts/check-env.js\n+++ b/scripts/check-env.js\n+const env = process.env;\n",
        workspace=DirWorkspace(tmp_path),
    )


# -- one-shot ------------------------------------------------------------------


def test_oneshot_parses_a_structured_verdict(submission):
    client = FakeClient(queue=[response([text_block(json.dumps(VERDICT_JSON))])])
    result = Reviewer(ReviewConfig(mode="oneshot"), client).review(submission)

    assert result.verdict.verdict == "unsafe"
    assert result.verdict.findings[0].category == "credential-exfiltration"
    assert result.steps == 1
    assert result.error is None
    assert result.usage.input_tokens == 100


def test_oneshot_requests_the_shared_schema_and_no_tools(submission):
    client = FakeClient(queue=[response([text_block(json.dumps(VERDICT_JSON))])])
    Reviewer(ReviewConfig(mode="oneshot"), client).review(submission)

    params = client.calls[0]
    assert params["output_config"]["format"]["schema"] is VERDICT_SCHEMA
    assert params["output_config"]["effort"] == "high"
    assert params["thinking"] == {"type": "adaptive"}
    assert "tools" not in params
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_no_thinking_disables_it_explicitly(submission):
    # Omitting `thinking` is not the same as disabling it: Opus 5 and Fable 5
    # run adaptive when the parameter is absent.
    client = FakeClient(queue=[response([text_block(json.dumps(VERDICT_JSON))])])
    Reviewer(ReviewConfig(mode="oneshot", thinking=False), client).review(submission)
    assert client.calls[0]["thinking"] == {"type": "disabled"}
    assert "effort" not in client.calls[0]["output_config"]


def test_oneshot_reports_unparseable_output_instead_of_crashing(submission):
    client = FakeClient(queue=[response([text_block("not json")])])
    result = Reviewer(ReviewConfig(mode="oneshot"), client).review(submission)

    assert result.verdict.verdict == "needs_human_review"
    assert result.error.startswith("parse_error")


def test_refusal_becomes_an_abstention(submission):
    refused = response(
        [],
        stop_reason="refusal",
        stop_details=SimpleNamespace(category="cyber", explanation="declined"),
    )
    result = Reviewer(ReviewConfig(mode="oneshot"), FakeClient(queue=[refused])).review(submission)

    assert result.verdict.verdict == "needs_human_review"
    assert result.error == "refusal"
    assert "cyber" in result.verdict.summary


def test_fallbacks_toggle_selects_the_endpoint(submission):
    on = FakeClient(queue=[response([text_block(json.dumps(VERDICT_JSON))])])
    Reviewer(ReviewConfig(mode="oneshot", fallbacks=True), on).review(submission)
    assert on.calls[0]["fallbacks"] == "default"

    off = FakeClient(queue=[response([text_block(json.dumps(VERDICT_JSON))])])
    Reviewer(ReviewConfig(mode="oneshot", fallbacks=False), off).review(submission)
    assert "fallbacks" not in off.calls[0]


# -- agent ---------------------------------------------------------------------


def test_agent_runs_tools_then_submits(submission):
    client = FakeClient(
        queue=[
            response([tool_block("list_files", {}, "t1")], stop_reason="tool_use"),
            response([tool_block("read_file", {"path": "scripts/check-env.js"}, "t2")],
                     stop_reason="tool_use"),
            response([tool_block("grep", {"pattern": "process.env"}, "t3")], stop_reason="tool_use"),
            response([tool_block("submit_verdict", VERDICT_JSON, "t4")], stop_reason="tool_use"),
        ]
    )
    result = Reviewer(ReviewConfig(mode="agent"), client).review(submission)

    assert result.verdict.verdict == "unsafe"
    assert result.steps == 4
    assert result.tool_calls[0].startswith("list_files")
    assert result.tool_calls[-1] == "submit_verdict"

    # the tool result for the read went back keyed to the right tool_use id
    second_call_messages = client.calls[2]["messages"]
    tool_result = second_call_messages[-1]["content"][0]
    assert tool_result["tool_use_id"] == "t2"
    assert "process.env" in tool_result["content"]
    assert tool_result["is_error"] is False


def test_agent_gets_explore_tools_plus_submit_verdict(submission):
    client = FakeClient(queue=[response([tool_block("submit_verdict", VERDICT_JSON)],
                                        stop_reason="tool_use")])
    Reviewer(ReviewConfig(mode="agent"), client).review(submission)

    names = [t["name"] for t in client.calls[0]["tools"]]
    assert names == ["list_files", "read_file", "grep", "submit_verdict"]
    assert client.calls[0]["tools"] is AGENT_TOOLS
    submit = client.calls[0]["tools"][-1]
    assert submit["strict"] is True


def test_tool_errors_are_returned_to_the_model_not_raised(submission):
    client = FakeClient(
        queue=[
            response([tool_block("read_file", {"path": "../../etc/passwd"}, "t1")],
                     stop_reason="tool_use"),
            response([tool_block("submit_verdict", VERDICT_JSON, "t2")], stop_reason="tool_use"),
        ]
    )
    result = Reviewer(ReviewConfig(mode="agent"), client).review(submission)

    tool_result = client.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "escapes the workspace root" in tool_result["content"]
    assert result.verdict.verdict == "unsafe"  # the review still completes


def test_agent_is_nudged_once_when_it_answers_in_prose(submission):
    client = FakeClient(
        queue=[
            response([text_block("Looks unsafe to me.")]),
            response([tool_block("submit_verdict", VERDICT_JSON, "t1")], stop_reason="tool_use"),
        ]
    )
    result = Reviewer(ReviewConfig(mode="agent"), client).review(submission)

    assert "submit_verdict now" in client.calls[1]["messages"][-1]["content"]
    assert result.verdict.verdict == "unsafe"


def test_agent_that_never_submits_abstains_with_an_error(submission):
    client = FakeClient(queue=[response([text_block("thinking about it")]) for _ in range(2)])
    result = Reviewer(ReviewConfig(mode="agent"), client).review(submission)

    assert result.verdict.verdict == "needs_human_review"
    assert result.error.startswith("no_verdict_tool_call")


def test_agent_stops_at_the_step_limit(submission):
    looping = [response([tool_block("grep", {"pattern": "x"}, f"t{i}")], stop_reason="tool_use")
               for i in range(5)]
    client = FakeClient(queue=looping)
    result = Reviewer(ReviewConfig(mode="agent", max_steps=3), client).review(submission)

    assert result.error == "step_limit"
    assert result.steps == 3
    assert len(client.calls) == 3


def test_invalid_verdict_payload_is_reported(submission):
    bad = {**VERDICT_JSON, "confidence": 4.2}  # out of the 0..1 range
    client = FakeClient(queue=[response([tool_block("submit_verdict", bad)], stop_reason="tool_use")])
    result = Reviewer(ReviewConfig(mode="agent"), client).review(submission)

    assert result.verdict.verdict == "needs_human_review"
    assert result.error.startswith("validation_error")


# -- scanners ------------------------------------------------------------------


def test_scanners_are_off_by_default(submission):
    """The LLM-only score is the baseline, so it must be the default."""
    client = FakeClient(queue=[response([tool_block("submit_verdict", VERDICT_JSON)],
                                        stop_reason="tool_use")])
    Reviewer(ReviewConfig(mode="agent"), client).review(submission)

    names = [t["name"] for t in client.calls[0]["tools"]]
    assert "run_scanner" not in names
    assert "run_scanner" not in client.calls[0]["system"][0]["text"]


def test_scanners_flag_adds_the_tool_and_the_rubric_section(submission):
    client = FakeClient(queue=[response([tool_block("submit_verdict", VERDICT_JSON)],
                                        stop_reason="tool_use")])
    Reviewer(ReviewConfig(mode="agent", scanners=True), client).review(submission)

    names = [t["name"] for t in client.calls[0]["tools"]]
    assert names == ["list_files", "read_file", "grep", "run_scanner", "submit_verdict"]
    system = client.calls[0]["system"][0]["text"]
    assert "Static analyzers" in system
    assert "evidence, not as a verdict" in system


def test_scanner_results_are_recorded_on_the_result(submission, monkeypatch):
    from abo import reviewer as reviewer_mod
    from abo.scanners import ScanResult, ScannerFinding

    fake = ScanResult(
        scanner="semgrep", config="p/python",
        findings=[ScannerFinding("semgrep", "avoid-pickle", "a.py", 3, "WARNING", "m")],
    )
    monkeypatch.setattr(reviewer_mod, "scan", lambda *a, **k: fake)

    client = FakeClient(
        queue=[
            response([tool_block("run_scanner", {"scanner": "semgrep", "config": "p/python"}, "t1")],
                     stop_reason="tool_use"),
            response([tool_block("submit_verdict", VERDICT_JSON, "t2")], stop_reason="tool_use"),
        ]
    )
    result = Reviewer(ReviewConfig(mode="agent", scanners=True), client).review(submission)

    assert len(result.scans) == 1
    assert result.scans[0].scanner == "semgrep"
    assert result.to_dict()["scans"][0]["findings"][0]["rule"] == "avoid-pickle"
    # the rendered scan went back to the model as a normal tool result
    tool_result = client.calls[1]["messages"][-1]["content"][0]
    assert "avoid-pickle" in tool_result["content"]
    assert tool_result["is_error"] is False


def test_a_missing_scanner_does_not_end_the_review(submission, monkeypatch):
    from abo import reviewer as reviewer_mod
    from abo.scanners import ScannerError

    def boom(*a, **k):
        raise ScannerError("semgrep is not installed on this machine.")

    monkeypatch.setattr(reviewer_mod, "scan", boom)
    client = FakeClient(
        queue=[
            response([tool_block("run_scanner", {"scanner": "semgrep"}, "t1")],
                     stop_reason="tool_use"),
            response([tool_block("submit_verdict", VERDICT_JSON, "t2")], stop_reason="tool_use"),
        ]
    )
    result = Reviewer(ReviewConfig(mode="agent", scanners=True), client).review(submission)

    tool_result = client.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "not installed" in tool_result["content"]
    assert result.verdict.verdict == "unsafe"  # the review still concluded


def test_scan_results_do_not_leak_between_concurrent_reviews(submission, monkeypatch):
    """run_eval shares one Reviewer across threads; scans must stay per-review."""
    from abo import reviewer as reviewer_mod
    from abo.scanners import ScanResult

    monkeypatch.setattr(reviewer_mod, "scan",
                        lambda *a, **k: ScanResult(scanner="semgrep", config="p/python"))
    rev = Reviewer(ReviewConfig(mode="agent", scanners=True), FakeClient())

    def fresh_client():
        return FakeClient(queue=[
            response([tool_block("run_scanner", {"scanner": "semgrep"}, "t1")],
                     stop_reason="tool_use"),
            response([tool_block("submit_verdict", VERDICT_JSON, "t2")], stop_reason="tool_use"),
        ])

    rev.provider.client = fresh_client()
    first = rev.review(submission)
    rev.provider.client = fresh_client()
    second = rev.review(submission)

    assert len(first.scans) == 1 and len(second.scans) == 1


# -- accounting ----------------------------------------------------------------


def test_usage_accumulates_across_agent_turns(submission):
    client = FakeClient(
        queue=[
            response([tool_block("grep", {"pattern": "x"}, "t1")], stop_reason="tool_use"),
            response([tool_block("submit_verdict", VERDICT_JSON, "t2")], stop_reason="tool_use"),
        ]
    )
    result = Reviewer(ReviewConfig(mode="agent"), client).review(submission)
    assert result.usage.input_tokens == 200
    assert result.usage.output_tokens == 100


def test_cost_uses_the_published_rates():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000,
                  cache_read_tokens=1_000_000, cache_write_tokens=1_000_000)
    # 5 + 25 + 0.5 + 6.25
    assert usage.cost("claude-opus-5") == pytest.approx(36.75)
    assert usage.cost("unknown-model") == 0.0
