"""Verdict schema shared by every reviewer mode.

Both the one-shot judge and the tool-using agent emit the *same* structure, so
their scores are directly comparable. The JSON Schema below is hand-written
rather than derived from the Pydantic models: it must stay free of ``$ref`` /
``$defs`` and nullable unions so it can be used both as an ``output_config``
response format and as a ``strict: true`` tool input schema.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

Severity = Literal["info", "low", "medium", "high", "critical"]
CaseLabel = Literal["safe", "unsafe"]
VerdictLabel = Literal["safe", "unsafe", "needs_human_review"]

#: Severities at or above this level make a verdict of "unsafe" mandatory.
BLOCKING_SEVERITIES = ("medium", "high", "critical")


class Finding(BaseModel):
    file: str
    line: int = Field(0, description="0 when not tied to a specific line")
    severity: Severity
    category: str
    description: str
    evidence: str

    def location(self) -> str:
        return f"{self.file}:{self.line}" if self.line else self.file


class Verdict(BaseModel):
    verdict: VerdictLabel
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    findings: list[Finding] = Field(default_factory=list)

    @field_validator("findings", mode="before")
    @classmethod
    def decode_stringified_findings(cls, value: Any) -> Any:
        """Accept a provider's accidentally JSON-encoded findings array.

        Some tool-call responses have returned the array as a string containing
        JSON. Decode only that transport mistake; the normal list validation
        below still checks every finding and rejects malformed values.
        """
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return value
            return decoded
        return value

    @property
    def flagged(self) -> bool:
        """True when this verdict would block a merge.

        ``needs_human_review`` counts as flagged: in a real gate it stops the
        merge just as ``unsafe`` does. Abstentions are still reported
        separately so you can see how often the reviewer punts.
        """
        return self.verdict != "safe"

    def max_severity(self) -> Optional[str]:
        order = ["info", "low", "medium", "high", "critical"]
        present = [f.severity for f in self.findings]
        if not present:
            return None
        return max(present, key=order.index)


VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["safe", "unsafe", "needs_human_review"],
            "description": (
                "'unsafe' if the change introduces at least one in-scope security "
                "issue of medium severity or higher; 'safe' if it does not; "
                "'needs_human_review' only if required context was unavailable."
            ),
        },
        "confidence": {
            "type": "number",
            "description": "0.0-1.0 probability that the verdict label is correct.",
        },
        "summary": {
            "type": "string",
            "description": "Two or three sentences: what the change does and why it got this verdict.",
        },
        "findings": {
            "type": "array",
            "description": "Security-relevant issues introduced by this change. Empty for a clean change.",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Path as it appears in the diff."},
                    "line": {
                        "type": "integer",
                        "description": "Line number in the post-change file, or 0 if not line-specific.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["info", "low", "medium", "high", "critical"],
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Short kebab-case slug, e.g. credential-exfiltration, auth-bypass, "
                            "command-injection, supply-chain, ci-secret-exposure, obfuscation, "
                            "prompt-injection, crypto-misuse, data-exposure."
                        ),
                    },
                    "description": {"type": "string", "description": "What is wrong and how it could be exploited."},
                    "evidence": {
                        "type": "string",
                        "description": "Verbatim quote from the diff or a file you read that supports this finding.",
                    },
                },
                "required": ["file", "line", "severity", "category", "description", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "confidence", "summary", "findings"],
    "additionalProperties": False,
}
