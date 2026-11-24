"""Load and validate the golden set (one JSON object per line)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .models import SEVERITIES, Expectations, GoldenCase
from .rubric import CRITERIA

CASE_KEYS = {"id", "category", "severity", "message", "customer_name", "expect", "rubric", "notes"}
EXPECT_KEYS = {
    "intent",
    "escalate",
    "must_include_any",
    "must_not_include",
    "must_match",
    "must_not_match",
    "actions_required",
    "actions_forbidden",
    "max_words",
}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class GoldenSetError(ValueError):
    """Raised with every problem found, so a broken set is fixed in one pass."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _str_list(value: Any, where: str, problems: list[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        problems.append(f"{where} must be a list of non-empty strings")
        return ()
    return tuple(value)


def _parse_expect(raw: Any, where: str, problems: list[str]) -> Expectations:
    if raw is None:
        return Expectations()
    if not isinstance(raw, dict):
        problems.append(f"{where}: expect must be an object")
        return Expectations()
    for key in sorted(set(raw) - EXPECT_KEYS):
        problems.append(f"{where}: unknown expect key '{key}'")

    groups_raw = raw.get("must_include_any") or []
    groups: list[tuple[str, ...]] = []
    if not isinstance(groups_raw, list):
        problems.append(f"{where}: must_include_any must be a list of lists")
    else:
        for i, group in enumerate(groups_raw):
            parsed = _str_list(group, f"{where}: must_include_any[{i}]", problems)
            if parsed:
                groups.append(parsed)

    patterns: dict[str, tuple[str, ...]] = {}
    for key in ("must_match", "must_not_match"):
        patterns[key] = _str_list(raw.get(key), f"{where}: {key}", problems)
        for pattern in patterns[key]:
            try:
                re.compile(pattern)
            except re.error as exc:
                problems.append(f"{where}: {key} has invalid regex '{pattern}': {exc}")

    escalate = raw.get("escalate")
    if escalate is not None and not isinstance(escalate, bool):
        problems.append(f"{where}: escalate must be true, false or omitted")
        escalate = None

    max_words = raw.get("max_words")
    if max_words is not None and (not isinstance(max_words, int) or max_words <= 0):
        problems.append(f"{where}: max_words must be a positive integer")
        max_words = None

    intent = raw.get("intent")
    if intent is not None and not isinstance(intent, str):
        problems.append(f"{where}: intent must be a string")
        intent = None

    return Expectations(
        intent=intent,
        escalate=escalate,
        must_include_any=tuple(groups),
        must_not_include=_str_list(raw.get("must_not_include"), f"{where}: must_not_include", problems),
        must_match=patterns["must_match"],
        must_not_match=patterns["must_not_match"],
        actions_required=_str_list(raw.get("actions_required"), f"{where}: actions_required", problems),
        actions_forbidden=_str_list(raw.get("actions_forbidden"), f"{where}: actions_forbidden", problems),
        max_words=max_words,
    )


def parse_cases(records: list[dict[str, Any]]) -> list[GoldenCase]:
    problems: list[str] = []
    cases: list[GoldenCase] = []
    seen: set[str] = set()
    for index, raw in enumerate(records, start=1):
        where = f"case {index}"
        if not isinstance(raw, dict):
            problems.append(f"{where}: must be a JSON object")
            continue
        case_id = raw.get("id")
        if not isinstance(case_id, str) or not ID_PATTERN.match(case_id):
            problems.append(f"{where}: id must be lowercase letters, digits and dashes")
            case_id = f"invalid-{index}"
        where = f"case '{case_id}'"
        if case_id in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(case_id)
        for key in sorted(set(raw) - CASE_KEYS):
            problems.append(f"{where}: unknown key '{key}'")
        for key in ("category", "message"):
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                problems.append(f"{where}: '{key}' is required")
        severity = raw.get("severity", "normal")
        if severity not in SEVERITIES:
            problems.append(f"{where}: severity must be one of {', '.join(SEVERITIES)}")
        rubric = _str_list(raw.get("rubric"), f"{where}: rubric", problems)
        for criterion in rubric:
            if criterion not in CRITERIA:
                problems.append(f"{where}: unknown rubric criterion '{criterion}'")
        expect = _parse_expect(raw.get("expect"), where, problems)
        cases.append(
            GoldenCase(
                id=case_id,
                category=str(raw.get("category", "")),
                severity=str(severity),
                message=str(raw.get("message", "")),
                customer_name=str(raw.get("customer_name", "Alex Sample")),
                expect=expect,
                rubric=rubric,
                notes=str(raw.get("notes", "")),
            )
        )
    if not records:
        problems.append("golden set is empty")
    if problems:
        raise GoldenSetError(problems)
    return cases


def load_golden(path: str | Path) -> list[GoldenCase]:
    records: list[dict[str, Any]] = []
    problems: list[str] = []
    text = Path(path).read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            problems.append(f"line {line_no}: invalid JSON ({exc.msg})")
    if problems:
        raise GoldenSetError(problems)
    return parse_cases(records)


def golden_hash(cases: list[GoldenCase]) -> str:
    """Short fingerprint so a report can warn when two runs used different sets."""
    payload = [
        [c.id, c.category, c.severity, c.message, c.customer_name, repr(c.expect), list(c.rubric)]
        for c in cases
    ]
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()[:12]
