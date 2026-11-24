"""Run the golden set through an agent and score every reply."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agents import Agent
from .checks import run_checks
from .golden import golden_hash
from .judge import Judge, JudgeError
from .models import AgentReply, CheckResult, GoldenCase, JudgeVerdict

SCHEMA_VERSION = 1
DEFAULT_JUDGE_PASS_MARK = 0.6


def _score_case(
    case: GoldenCase, agent: Agent, judge: Judge | None, judge_pass_mark: float
) -> dict[str, Any]:
    context = {"case_id": case.id, "customer_name": case.customer_name}
    agent_error: str | None = None
    try:
        reply = AgentReply.coerce(agent(case.message, context))
    except Exception as exc:  # a crashing agent is a failed case, not a failed run
        agent_error = f"{type(exc).__name__}: {exc}"
        reply = AgentReply(text="")

    checks: list[CheckResult] = []
    if agent_error:
        checks.append(CheckResult("agent_responded", False, agent_error))
    checks.extend(run_checks(case, reply))
    checks_passed = all(c.passed for c in checks)

    verdict: JudgeVerdict | None = None
    if judge is not None and case.rubric and not agent_error:
        try:
            verdict = judge.grade(case, reply)
        except JudgeError as exc:
            verdict = JudgeVerdict(judge=judge.name, error=str(exc))
    judge_passed = verdict is None or (verdict.error is None and verdict.overall >= judge_pass_mark)

    return {
        "id": case.id,
        "category": case.category,
        "severity": case.severity,
        "passed": checks_passed and judge_passed,
        "checks_passed": checks_passed,
        "judge_passed": judge_passed,
        "checks": [c.to_dict() for c in checks],
        "judge": verdict.to_dict() if verdict else None,
        "reply": reply.to_dict(),
    }


def summarize(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(case_results)
    passed = sum(1 for r in case_results if r["passed"])
    judged = [r["judge"]["overall"] for r in case_results if r["judge"] and not r["judge"]["error"]]
    critical = [r for r in case_results if r["severity"] == "critical"]
    by_category: dict[str, dict[str, int]] = {}
    for result in case_results:
        bucket = by_category.setdefault(result["category"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += 1 if result["passed"] else 0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "mean_judge_score": round(sum(judged) / len(judged), 4) if judged else None,
        "judge_errors": sum(1 for r in case_results if r["judge"] and r["judge"]["error"]),
        "critical_total": len(critical),
        "critical_passed": sum(1 for r in critical if r["passed"]),
        "by_category": dict(sorted(by_category.items())),
    }


def run_eval(
    cases: list[GoldenCase],
    agent: Agent,
    judge: Judge | None,
    *,
    label: str,
    agent_name: str,
    judge_pass_mark: float = DEFAULT_JUDGE_PASS_MARK,
) -> dict[str, Any]:
    """Return a run result: plain JSON-serialisable data, no timestamps, so reruns diff cleanly."""
    case_results = [_score_case(case, agent, judge, judge_pass_mark) for case in cases]
    return {
        "schema_version": SCHEMA_VERSION,
        "label": label,
        "agent": agent_name,
        "judge": judge.name if judge else "none",
        "judge_pass_mark": judge_pass_mark,
        "golden_hash": golden_hash(cases),
        "summary": summarize(case_results),
        "cases": case_results,
    }


def save_run(run: dict[str, Any], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(run, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def load_run(path: str | Path) -> dict[str, Any]:
    run = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(run, dict) or run.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{path} is not a run file this version can read")
    for key in ("label", "summary", "cases"):
        if key not in run:
            raise ValueError(f"{path} is missing '{key}'")
    return run
