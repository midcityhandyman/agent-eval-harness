"""Compare a candidate run against a baseline run and decide whether it regressed."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Thresholds:
    # How far the overall pass rate may fall before the gate fails (0.0 = not at all).
    max_pass_rate_drop: float = 0.0
    # How far the mean judge score (0..1) may fall before the gate fails.
    max_judge_drop: float = 0.05
    # A single case whose judge score falls by more than this is listed as drift.
    case_judge_drop: float = 0.25
    # Fail when a critical case fails in the candidate, even if it also failed before.
    fail_on_critical: bool = True
    # Treat per-case judge drift as a gate failure instead of a warning.
    fail_on_judge_drift: bool = False


@dataclass
class Comparison:
    baseline_label: str
    candidate_label: str
    baseline_summary: dict[str, Any]
    candidate_summary: dict[str, Any]
    thresholds: Thresholds
    regressions: list[dict[str, Any]] = field(default_factory=list)
    critical_failures: list[dict[str, Any]] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    still_failing: list[dict[str, Any]] = field(default_factory=list)
    judge_drift: list[dict[str, Any]] = field(default_factory=list)
    missing_cases: list[str] = field(default_factory=list)
    new_cases: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def regressed(self) -> bool:
        return bool(self.reasons)

    @property
    def pass_rate_delta(self) -> float:
        return round(self.candidate_summary["pass_rate"] - self.baseline_summary["pass_rate"], 4)

    @property
    def judge_delta(self) -> float | None:
        before = self.baseline_summary.get("mean_judge_score")
        after = self.candidate_summary.get("mean_judge_score")
        if before is None or after is None:
            return None
        return round(after - before, 4)


def _failure_reasons(case: dict[str, Any]) -> list[str]:
    reasons = []
    for check in case.get("checks", []):
        if not check["passed"]:
            detail = f" ({check['detail']})" if check.get("detail") else ""
            reasons.append(f"{check['name']}{detail}")
    judge = case.get("judge")
    if judge and not case.get("judge_passed", True):
        if judge.get("error"):
            reasons.append(f"judge error ({judge['error']})")
        else:
            low = [f"{k}={v}" for k, v in judge.get("scores", {}).items() if v <= 2]
            reasons.append(f"judge score {judge['overall']:.2f}" + (f" ({', '.join(low)})" if low else ""))
    return reasons


def _brief(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["id"],
        "category": case["category"],
        "severity": case["severity"],
        "reasons": _failure_reasons(case),
    }


def _judge_score(case: dict[str, Any]) -> float | None:
    judge = case.get("judge")
    if not judge or judge.get("error"):
        return None
    return judge["overall"]


def compare_runs(
    baseline: dict[str, Any], candidate: dict[str, Any], thresholds: Thresholds | None = None
) -> Comparison:
    thresholds = thresholds or Thresholds()
    result = Comparison(
        baseline_label=baseline["label"],
        candidate_label=candidate["label"],
        baseline_summary=baseline["summary"],
        candidate_summary=candidate["summary"],
        thresholds=thresholds,
    )
    before = {c["id"]: c for c in baseline["cases"]}
    after = {c["id"]: c for c in candidate["cases"]}

    if baseline.get("golden_hash") != candidate.get("golden_hash"):
        result.warnings.append(
            "the two runs used different golden sets, so aggregate numbers are not like for like"
        )
    if baseline.get("judge") != candidate.get("judge"):
        result.warnings.append(
            f"the runs used different judges ({baseline.get('judge')} vs {candidate.get('judge')}), "
            "so judge scores are not comparable"
        )
    marks = (baseline.get("judge_pass_mark"), candidate.get("judge_pass_mark"))
    if marks[0] != marks[1]:
        result.warnings.append(
            f"the runs used different judge pass marks ({marks[0]} vs {marks[1]}), "
            "so a case can pass or fail without the reply changing"
        )
    judge_errors = candidate["summary"].get("judge_errors", 0)
    if judge_errors:
        result.warnings.append(f"the judge errored on {judge_errors} candidate case(s)")

    result.missing_cases = sorted(set(before) - set(after))
    result.new_cases = sorted(set(after) - set(before))

    for case_id, case in after.items():
        old = before.get(case_id)
        if not case["passed"]:
            if case["severity"] == "critical":
                result.critical_failures.append(_brief(case))
            if old is not None and old["passed"]:
                result.regressions.append(_brief(case))
            else:
                result.still_failing.append(_brief(case))
        elif old is not None and not old["passed"]:
            result.improvements.append(case_id)

        if old is not None:
            was, now = _judge_score(old), _judge_score(case)
            if was is not None and now is not None and was - now > thresholds.case_judge_drop:
                result.judge_drift.append(
                    {"id": case_id, "before": was, "after": now, "delta": round(now - was, 4)}
                )

    if result.regressions:
        ids = ", ".join(r["id"] for r in result.regressions)
        result.reasons.append(f"{len(result.regressions)} case(s) passed before and fail now: {ids}")
    if thresholds.fail_on_critical and result.critical_failures:
        ids = ", ".join(r["id"] for r in result.critical_failures)
        result.reasons.append(f"{len(result.critical_failures)} critical case(s) fail: {ids}")
    if result.missing_cases:
        result.reasons.append(
            "candidate run is missing baseline case(s): " + ", ".join(result.missing_cases)
        )
    if -result.pass_rate_delta > thresholds.max_pass_rate_drop + 1e-9:
        result.reasons.append(
            f"pass rate fell by {-result.pass_rate_delta:.1%} "
            f"(allowed {thresholds.max_pass_rate_drop:.1%})"
        )
    delta = result.judge_delta
    if delta is not None and -delta > thresholds.max_judge_drop + 1e-9:
        result.reasons.append(
            f"mean judge score fell by {-delta:.3f} (allowed {thresholds.max_judge_drop:.3f})"
        )
    if thresholds.fail_on_judge_drift and result.judge_drift:
        ids = ", ".join(d["id"] for d in result.judge_drift)
        result.reasons.append(f"judge score dropped sharply on: {ids}")
    return result
