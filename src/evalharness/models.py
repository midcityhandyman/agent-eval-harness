"""Plain data types shared by every part of the harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITIES = ("critical", "normal")


@dataclass(frozen=True)
class Expectations:
    """Deterministic expectations for one golden case. Empty fields are not checked."""

    intent: str | None = None
    escalate: bool | None = None
    # Each inner group passes when at least one of its phrases appears in the reply.
    must_include_any: tuple[tuple[str, ...], ...] = ()
    must_not_include: tuple[str, ...] = ()
    must_match: tuple[str, ...] = ()
    must_not_match: tuple[str, ...] = ()
    actions_required: tuple[str, ...] = ()
    actions_forbidden: tuple[str, ...] = ()
    max_words: int | None = None


@dataclass(frozen=True)
class GoldenCase:
    id: str
    category: str
    severity: str
    message: str
    customer_name: str
    expect: Expectations
    rubric: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class AgentReply:
    """What an agent under test returns for one customer message."""

    text: str
    intent: str | None = None
    actions: tuple[str, ...] = ()
    escalate: bool = False

    @classmethod
    def coerce(cls, value: Any) -> "AgentReply":
        """Accept an AgentReply, a dict with the same keys, or a bare string."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(text=value)
        if isinstance(value, dict):
            if "text" not in value:
                raise TypeError("agent reply dict needs a 'text' key")
            return cls(
                text=str(value["text"]),
                intent=value.get("intent"),
                actions=tuple(value.get("actions") or ()),
                escalate=bool(value.get("escalate", False)),
            )
        raise TypeError(f"unsupported agent reply type: {type(value).__name__}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "intent": self.intent,
            "actions": list(self.actions),
            "escalate": self.escalate,
        }


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "skipped": self.skipped,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class JudgeVerdict:
    judge: str
    scores: dict[str, int] = field(default_factory=dict)
    overall: float = 0.0
    rationale: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "judge": self.judge,
            "scores": dict(self.scores),
            "overall": self.overall,
            "rationale": self.rationale,
            "error": self.error,
        }
