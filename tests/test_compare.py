import copy

import pytest

from evalharness.compare import Thresholds, compare_runs
from evalharness.judge import MockJudge
from evalharness.report import render_comparison_markdown, render_comparison_text
from evalharness.runner import run_eval, summarize
from evalharness.sample_agents import improved_agent, regressed_agent, stable_agent


def case(case_id, passed=True, severity="normal", judge=None):
    checks = [{"name": "must_match", "passed": passed, "skipped": False,
               "detail": "" if passed else "pattern not found"}]
    verdict = None
    if judge is not None:
        verdict = {"judge": "mock", "scores": {"concise": 5}, "overall": judge,
                   "rationale": "", "error": None}
    return {"id": case_id, "category": "test", "severity": severity, "passed": passed,
            "checks_passed": passed, "judge_passed": True, "checks": checks, "judge": verdict,
            "reply": {"text": "x", "intent": None, "actions": [], "escalate": False}}


def make_run(label, cases, golden_hash="abc", judge="mock"):
    return {"schema_version": 1, "label": label, "agent": "test", "judge": judge,
            "judge_pass_mark": 0.6, "golden_hash": golden_hash,
            "summary": summarize(cases), "cases": cases}


def test_identical_runs_do_not_regress():
    run = make_run("a", [case("one"), case("two", passed=False)])
    result = compare_runs(run, copy.deepcopy(run))
    assert not result.regressed
    assert [c["id"] for c in result.still_failing] == ["two"]
    assert result.pass_rate_delta == 0


def test_case_that_flips_to_failing_is_a_regression():
    base = make_run("base", [case("one"), case("two")])
    cand = make_run("cand", [case("one"), case("two", passed=False)])
    result = compare_runs(base, cand)
    assert result.regressed
    assert result.regressions[0]["id"] == "two"
    assert result.regressions[0]["reasons"] == ["must_match (pattern not found)"]


def test_one_fix_does_not_hide_one_break():
    base = make_run("base", [case("one"), case("two", passed=False)])
    cand = make_run("cand", [case("one", passed=False), case("two")])
    result = compare_runs(base, cand)
    assert result.pass_rate_delta == 0
    assert result.improvements == ["two"]
    assert result.regressed and "one" in result.reasons[0]


def test_improvement_only_passes_the_gate():
    base = make_run("base", [case("one"), case("two", passed=False)])
    cand = make_run("cand", [case("one"), case("two")])
    result = compare_runs(base, cand)
    assert not result.regressed and result.improvements == ["two"]


def test_critical_failure_blocks_even_when_it_failed_before():
    cases = [case("gas", passed=False, severity="critical")]
    base, cand = make_run("base", cases), make_run("cand", copy.deepcopy(cases))
    assert compare_runs(base, cand).regressed
    relaxed = compare_runs(base, cand, Thresholds(fail_on_critical=False))
    assert not relaxed.regressed


def test_missing_and_new_cases():
    base = make_run("base", [case("one"), case("two")])
    cand = make_run("cand", [case("one"), case("three")])
    result = compare_runs(base, cand)
    assert result.missing_cases == ["two"] and result.new_cases == ["three"]
    assert any("missing baseline case" in r for r in result.reasons)


def test_new_failing_case_is_not_called_a_regression():
    base = make_run("base", [case("one")])
    cand = make_run("cand", [case("one"), case("fresh", passed=False)])
    result = compare_runs(base, cand, Thresholds(max_pass_rate_drop=1.0))
    assert result.regressions == [] and not result.regressed
    assert [c["id"] for c in result.still_failing] == ["fresh"]


def test_pass_rate_tolerance():
    base = make_run("base", [case(str(i)) for i in range(10)])
    cand_cases = [case(str(i)) for i in range(10)]
    cand_cases[0] = case("0", passed=False)
    cand = make_run("cand", cand_cases)
    strict = compare_runs(base, cand)
    assert any("pass rate fell" in r for r in strict.reasons)
    loose = compare_runs(base, cand, Thresholds(max_pass_rate_drop=0.1))
    assert not any("pass rate fell" in r for r in loose.reasons)


def test_mean_judge_drop_fails_and_case_drift_is_listed():
    base = make_run("base", [case("one", judge=1.0), case("two", judge=1.0)])
    cand = make_run("cand", [case("one", judge=1.0), case("two", judge=0.7)])
    result = compare_runs(base, cand)
    assert result.judge_delta == pytest.approx(-0.15)
    assert any("mean judge score fell" in r for r in result.reasons)
    assert [d["id"] for d in result.judge_drift] == ["two"]

    small = make_run("cand", [case("one", judge=1.0), case("two", judge=0.95)])
    assert not compare_runs(base, small).regressed


def test_judge_drift_only_fails_when_asked():
    base = make_run("base", [case(str(i), judge=1.0) for i in range(10)])
    cand_cases = [case(str(i), judge=1.0) for i in range(10)]
    cand_cases[3] = case("3", judge=0.7)
    cand = make_run("cand", cand_cases)
    assert not compare_runs(base, cand).regressed
    assert compare_runs(base, cand, Thresholds(fail_on_judge_drift=True)).regressed


def test_warnings_for_mismatched_golden_set_and_judge():
    base = make_run("base", [case("one")], golden_hash="aaa", judge="mock")
    cand = make_run("cand", [case("one")], golden_hash="bbb", judge="claude")
    result = compare_runs(base, cand)
    assert len(result.warnings) == 2 and not result.regressed


def test_end_to_end_with_sample_agents(golden_cases):
    def run(agent, label):
        return run_eval(golden_cases, agent, MockJudge(), label=label, agent_name=label)

    baseline = run(stable_agent, "baseline")
    bad = compare_runs(baseline, run(regressed_agent, "regressed"))
    assert bad.regressed
    assert {r["id"] for r in bad.regressions} == {
        "quote-simple", "quote-pushy", "emergency-gas-with-price"}
    assert [c["id"] for c in bad.critical_failures] == ["emergency-gas-with-price"]
    assert bad.improvements == ["reschedule-basic"]

    good = compare_runs(baseline, run(improved_agent, "improved"))
    assert not good.regressed and good.improvements == ["reschedule-basic"]


def test_reports_render_verdict_and_tables(golden_cases):
    def run(agent, label):
        return run_eval(golden_cases, agent, MockJudge(), label=label, agent_name=label)

    bad = compare_runs(run(stable_agent, "baseline"), run(regressed_agent, "regressed"))
    markdown = render_comparison_markdown(bad)
    assert "**Verdict: REGRESSION**" in markdown
    assert "## Regressions" in markdown and "| emergency-gas-with-price |" in markdown
    assert "## Improvements" in markdown
    assert chr(0x2014) not in markdown
    text = render_comparison_text(bad)
    assert text.splitlines()[0].startswith("Compare 'baseline'")
    assert "VERDICT: REGRESSION" in text

    good = compare_runs(run(stable_agent, "baseline"), run(improved_agent, "improved"))
    assert "**Verdict: OK**" in render_comparison_markdown(good)
    assert "VERDICT: OK" in render_comparison_text(good)
