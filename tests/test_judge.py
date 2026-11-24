import json
from types import SimpleNamespace

import pytest

from evalharness.judge import ClaudeJudge, JudgeError, MockJudge, make_judge
from evalharness.models import AgentReply
from evalharness.rubric import CRITERIA, overall_from_scores


def test_overall_maps_scores_to_zero_one():
    assert overall_from_scores({"a": 5, "b": 5}) == 1.0
    assert overall_from_scores({"a": 1}) == 0.0
    assert overall_from_scores({"a": 3, "b": 5}) == 0.75
    assert overall_from_scores({}) == 1.0


def test_mock_judge_implements_every_criterion(make_case):
    case = make_case(rubric=tuple(CRITERIA))
    verdict = MockJudge().grade(case, AgentReply("I'm sorry. Please leave and call 911."))
    assert set(verdict.scores) == set(CRITERIA)
    assert all(1 <= s <= 5 for s in verdict.scores.values())


def test_mock_judge_is_deterministic(make_case):
    case = make_case(rubric=("empathy", "clear_next_step", "concise"))
    reply = AgentReply("I'm sorry about that. I have opened a ticket and we will call you.")
    assert MockJudge().grade(case, reply) == MockJudge().grade(case, reply)


def test_mock_judge_separates_good_from_bad(make_case):
    judge = MockJudge()
    promise = make_case(rubric=("no_overpromise",))
    assert judge.grade(promise, AgentReply("It is $149, guaranteed.")).overall == 0.0
    assert judge.grade(promise, AgentReply("A technician needs to look first.")).overall == 1.0

    safety = make_case(rubric=("safety_first",))
    assert judge.grade(safety, AgentReply("Leave now and call 911.")).scores["safety_first"] == 5
    assert judge.grade(safety, AgentReply("Leave the house.")).scores["safety_first"] == 3
    assert judge.grade(safety, AgentReply("We can book a visit.")).scores["safety_first"] == 1

    tone = make_case(rubric=("professional_tone",))
    assert judge.grade(tone, AgentReply("Calm down.")).scores["professional_tone"] == 1
    assert judge.grade(tone, AgentReply("STOP YELLING RIGHT THERE")).scores["professional_tone"] == 1


def test_make_judge_selects_by_name_and_env(monkeypatch):
    assert make_judge("none") is None
    assert isinstance(make_judge("mock"), MockJudge)
    monkeypatch.setenv("EVAL_JUDGE", "none")
    assert make_judge(None) is None
    monkeypatch.delenv("EVAL_JUDGE")
    assert isinstance(make_judge(None), MockJudge)
    with pytest.raises(ValueError):
        make_judge("oracle")


class FakeClient:
    """Stands in for the SDK client so ClaudeJudge runs with no network and no key."""

    def __init__(self, payload=None, stop_reason="end_turn", raises=None):
        self.calls = []
        self._payload = payload
        self._stop_reason = stop_reason
        self._raises = raises
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises:
            raise self._raises
        content = []
        if self._payload is not None:
            text = self._payload if isinstance(self._payload, str) else json.dumps(self._payload)
            content.append(SimpleNamespace(type="text", text=text))
        return SimpleNamespace(stop_reason=self._stop_reason, content=content)


def test_claude_judge_parses_structured_scores(make_case):
    case = make_case(rubric=("empathy", "concise"))
    client = FakeClient(
        {
            "scores": [
                {"criterion": "empathy", "score": 4},
                {"criterion": "concise", "score": 5},
            ],
            "rationale": "Warm and short.",
        }
    )
    judge = ClaudeJudge(model="test-model", client=client)
    verdict = judge.grade(case, AgentReply("I'm sorry. We will call you."))
    assert verdict.judge == "claude"
    assert verdict.scores == {"empathy": 4, "concise": 5}
    assert verdict.overall == 0.875
    assert verdict.rationale == "Warm and short."

    call = client.calls[0]
    assert call["model"] == "test-model"
    assert call["output_config"]["format"]["type"] == "json_schema"
    sent = json.loads(call["messages"][0]["content"])
    assert sent["customer_message"] == case.message
    assert set(sent["criteria"]) == {"empathy", "concise"}


def test_claude_judge_skips_the_call_when_there_is_no_rubric(make_case):
    client = FakeClient()
    verdict = ClaudeJudge(client=client).grade(make_case(), AgentReply("ok"))
    assert verdict.overall == 1.0 and client.calls == []


@pytest.mark.parametrize(
    "client, message",
    [
        (FakeClient({"scores": [], "rationale": ""}, stop_reason="refusal"), "declined"),
        (FakeClient("{not json"), "could not parse"),
        (FakeClient({"scores": [{"criterion": "empathy", "score": 3}], "rationale": ""}), "skipped"),
        (FakeClient(None), "no text block"),
        (FakeClient(raises=RuntimeError("boom")), "boom"),
    ],
)
def test_claude_judge_turns_bad_responses_into_judge_errors(make_case, client, message):
    case = make_case(rubric=("empathy", "concise"))
    with pytest.raises(JudgeError, match=message):
        ClaudeJudge(client=client).grade(case, AgentReply("ok"))
