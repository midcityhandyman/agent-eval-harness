import json

import pytest

from evalharness.agents import AgentLoadError, ReplayAgent, load_agent
from evalharness.judge import JudgeError, MockJudge
from evalharness.models import AgentReply
from evalharness.runner import load_run, run_eval, save_run
from evalharness.sample_agents import improved_agent, regressed_agent, stable_agent


def run(cases, agent, judge=None, label="t"):
    return run_eval(cases, agent, judge or MockJudge(), label=label, agent_name="test")


def test_stable_agent_has_exactly_the_one_known_gap(golden_cases):
    result = run(golden_cases, stable_agent)
    failing = [c["id"] for c in result["cases"] if not c["passed"]]
    assert failing == ["reschedule-basic"]
    assert result["summary"]["critical_passed"] == result["summary"]["critical_total"]


def test_improved_agent_passes_everything(golden_cases):
    assert run(golden_cases, improved_agent)["summary"]["failed"] == 0


def test_regressed_agent_fails_pricing_and_a_critical_case(golden_cases):
    result = run(golden_cases, regressed_agent)
    failing = {c["id"] for c in result["cases"] if not c["passed"]}
    assert failing == {"quote-simple", "quote-pushy", "emergency-gas-with-price"}
    assert result["summary"]["critical_passed"] == result["summary"]["critical_total"] - 1


def test_runs_are_reproducible(golden_cases):
    assert run(golden_cases, stable_agent) == run(golden_cases, stable_agent)


def test_summary_counts_and_categories(make_case):
    cases = [make_case("a", must_match=(r"\?",)), make_case("b", severity="critical")]
    result = run(cases, lambda message, context: "No question here.")
    summary = result["summary"]
    assert (summary["total"], summary["passed"], summary["failed"]) == (2, 1, 1)
    assert summary["pass_rate"] == 0.5
    assert summary["by_category"] == {"test": {"total": 2, "passed": 1}}
    assert summary["mean_judge_score"] is None  # no rubric on these cases


def test_agent_may_return_str_dict_or_reply(make_case):
    case = make_case(actions_required=("x",))
    for value in ({"text": "hi", "actions": ["x"]}, AgentReply("hi", actions=("x",))):
        assert run([case], lambda m, c, v=value: v)["cases"][0]["passed"]
    assert not run([case], lambda m, c: "hi")["cases"][0]["passed"]


def test_crashing_agent_fails_the_case_not_the_run(make_case):
    def broken(message, context):
        raise RuntimeError("upstream timeout")

    result = run([make_case(rubric=("concise",))], broken)
    case = result["cases"][0]
    assert not case["passed"]
    assert case["checks"][0]["name"] == "agent_responded"
    assert "upstream timeout" in case["checks"][0]["detail"]
    assert case["judge"] is None


def test_low_judge_score_fails_an_otherwise_clean_case(make_case):
    case = make_case(rubric=("no_overpromise",))
    result = run([case], lambda m, c: "Fixed by noon, guaranteed.")
    assert result["cases"][0]["checks_passed"]
    assert not result["cases"][0]["judge_passed"]
    assert not result["cases"][0]["passed"]


def test_judge_error_is_recorded_and_fails_the_case(make_case):
    class FlakyJudge:
        name = "flaky"

        def grade(self, case, reply):
            raise JudgeError("rate limited")

    result = run([make_case(rubric=("concise",))], lambda m, c: "ok", judge=FlakyJudge())
    assert result["cases"][0]["judge"]["error"] == "rate limited"
    assert not result["cases"][0]["passed"]
    assert result["summary"]["judge_errors"] == 1


def test_no_judge_means_checks_decide(make_case):
    result = run_eval([make_case(rubric=("no_overpromise",))], lambda m, c: "Guaranteed.",
                      None, label="t", agent_name="test")
    assert result["judge"] == "none" and result["cases"][0]["passed"]


def test_save_and_load_round_trip(tmp_path, golden_cases):
    result = run(golden_cases, stable_agent)
    path = tmp_path / "nested" / "run.json"
    save_run(result, path)
    assert load_run(path) == result
    path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_run(path)


def test_load_agent_by_spec():
    assert load_agent("evalharness.sample_agents:stable_agent") is stable_agent
    for spec in ("no_colon", "evalharness.nope:agent", "evalharness.sample_agents:missing"):
        with pytest.raises(AgentLoadError):
            load_agent(spec)


def test_replay_agent_serves_recorded_replies(tmp_path, make_case):
    path = tmp_path / "replies.jsonl"
    path.write_text(
        json.dumps({"id": "a", "text": "Which day works?", "actions": ["offer_booking_slots"]}) + "\n",
        encoding="utf-8",
    )
    agent = ReplayAgent(path)
    cases = [make_case("a", actions_required=("offer_booking_slots",)), make_case("b")]
    result = run(cases, agent)
    assert result["cases"][0]["passed"]
    assert "no recorded reply" in result["cases"][1]["checks"][0]["detail"]

    path.write_text('{"text": "missing id"}\n', encoding="utf-8")
    with pytest.raises(AgentLoadError):
        ReplayAgent(path)
