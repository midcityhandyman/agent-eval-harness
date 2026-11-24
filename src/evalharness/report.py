"""Render run summaries and regression comparisons as text and markdown."""

from __future__ import annotations

from typing import Any

from .compare import Comparison


def _pct(value: float) -> str:
    return f"{value:.1%}"


def _score(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _signed(value: float | None, as_pct: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.1%}" if as_pct else f"{value:+.3f}"


def render_run_text(run: dict[str, Any]) -> str:
    summary = run["summary"]
    lines = [
        f"Run '{run['label']}'  agent={run['agent']}  judge={run['judge']}  golden={run['golden_hash']}",
        f"  cases passed : {summary['passed']}/{summary['total']} ({_pct(summary['pass_rate'])})",
        f"  critical     : {summary['critical_passed']}/{summary['critical_total']}",
        f"  judge score  : {_score(summary['mean_judge_score'])}",
    ]
    lines.append("  by category  :")
    for category, bucket in summary["by_category"].items():
        lines.append(f"    {category:<12} {bucket['passed']}/{bucket['total']}")
    failed = [c for c in run["cases"] if not c["passed"]]
    if failed:
        lines.append("  failing cases:")
        for case in failed:
            bad = [c["name"] for c in case["checks"] if not c["passed"]]
            if not case.get("judge_passed", True):
                bad.append("judge")
            lines.append(f"    {case['id']} [{case['severity']}]: {', '.join(bad)}")
    return "\n".join(lines)


def render_comparison_text(cmp: Comparison) -> str:
    base, cand = cmp.baseline_summary, cmp.candidate_summary
    lines = [
        f"Compare '{cmp.baseline_label}' (baseline) -> '{cmp.candidate_label}' (candidate)",
        f"  pass rate   : {_pct(base['pass_rate'])} -> {_pct(cand['pass_rate'])} "
        f"({_signed(cmp.pass_rate_delta, as_pct=True)})",
        f"  judge score : {_score(base['mean_judge_score'])} -> {_score(cand['mean_judge_score'])} "
        f"({_signed(cmp.judge_delta)})",
        f"  critical    : {base['critical_passed']}/{base['critical_total']} -> "
        f"{cand['critical_passed']}/{cand['critical_total']}",
    ]
    if cmp.regressions:
        lines.append("  regressions (passed before, fail now):")
        for item in cmp.regressions:
            lines.append(f"    - {item['id']} [{item['severity']}]")
            lines.extend(f"        {reason}" for reason in item["reasons"])
    if cmp.improvements:
        lines.append("  improvements (failed before, pass now): " + ", ".join(cmp.improvements))
    if cmp.still_failing:
        lines.append("  still failing: " + ", ".join(i["id"] for i in cmp.still_failing))
    if cmp.judge_drift:
        lines.append("  judge drift:")
        for item in cmp.judge_drift:
            lines.append(f"    - {item['id']}: {item['before']:.2f} -> {item['after']:.2f}")
    if cmp.new_cases:
        lines.append("  new cases: " + ", ".join(cmp.new_cases))
    for warning in cmp.warnings:
        lines.append(f"  warning: {warning}")
    if cmp.regressed:
        lines.append("VERDICT: REGRESSION")
        lines.extend(f"  - {reason}" for reason in cmp.reasons)
    else:
        lines.append("VERDICT: OK (no regression)")
    return "\n".join(lines)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_comparison_markdown(cmp: Comparison) -> str:
    base, cand = cmp.baseline_summary, cmp.candidate_summary
    verdict = "REGRESSION" if cmp.regressed else "OK"
    out = [
        "# Agent eval regression report",
        "",
        f"**Verdict: {verdict}**",
        "",
        f"Baseline `{cmp.baseline_label}` compared with candidate `{cmp.candidate_label}`.",
        "",
    ]
    if cmp.reasons:
        out.append("## Why the gate failed")
        out.append("")
        out.extend(f"- {reason}" for reason in cmp.reasons)
        out.append("")
    out += [
        "## Summary",
        "",
        "| Metric | Baseline | Candidate | Change |",
        "| --- | --- | --- | --- |",
        f"| Cases passed | {base['passed']}/{base['total']} | {cand['passed']}/{cand['total']} | "
        f"{cand['passed'] - base['passed']:+d} |",
        f"| Pass rate | {_pct(base['pass_rate'])} | {_pct(cand['pass_rate'])} | "
        f"{_signed(cmp.pass_rate_delta, as_pct=True)} |",
        f"| Critical cases passed | {base['critical_passed']}/{base['critical_total']} | "
        f"{cand['critical_passed']}/{cand['critical_total']} | "
        f"{cand['critical_passed'] - base['critical_passed']:+d} |",
        f"| Mean judge score | {_score(base['mean_judge_score'])} | "
        f"{_score(cand['mean_judge_score'])} | {_signed(cmp.judge_delta)} |",
        "",
    ]
    if cmp.regressions:
        out += [
            "## Regressions",
            "",
            "Cases that passed in the baseline and fail in the candidate.",
            "",
            "| Case | Category | Severity | What failed |",
            "| --- | --- | --- | --- |",
        ]
        for item in cmp.regressions:
            out.append(
                f"| {item['id']} | {item['category']} | {item['severity']} | "
                f"{_cell('; '.join(item['reasons']))} |"
            )
        out.append("")
    if cmp.improvements:
        out += ["## Improvements", "", "Cases that failed in the baseline and pass now.", ""]
        out.extend(f"- {case_id}" for case_id in cmp.improvements)
        out.append("")
    if cmp.still_failing:
        out += ["## Still failing", "", "Failing in the candidate and not passing in the baseline.", ""]
        out.extend(
            f"- {item['id']} ({item['severity']}): {'; '.join(item['reasons'])}"
            for item in cmp.still_failing
        )
        out.append("")
    if cmp.judge_drift:
        out += [
            "## Judge drift",
            "",
            f"Cases whose judge score fell by more than {cmp.thresholds.case_judge_drop:.2f}.",
            "",
            "| Case | Before | After | Change |",
            "| --- | --- | --- | --- |",
        ]
        for item in cmp.judge_drift:
            out.append(
                f"| {item['id']} | {item['before']:.2f} | {item['after']:.2f} | {item['delta']:+.2f} |"
            )
        out.append("")
    if cmp.new_cases or cmp.missing_cases or cmp.warnings:
        out += ["## Notes", ""]
        if cmp.new_cases:
            out.append("- New cases (not in baseline): " + ", ".join(cmp.new_cases))
        if cmp.missing_cases:
            out.append("- Missing from candidate: " + ", ".join(cmp.missing_cases))
        out.extend(f"- Warning: {warning}" for warning in cmp.warnings)
        out.append("")
    return "\n".join(out)
