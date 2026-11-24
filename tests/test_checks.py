from evalharness.checks import run_checks
from evalharness.models import AgentReply


def results_by_name(case, reply):
    return {r.name: r for r in run_checks(case, reply)}


def test_global_checks_pass_on_a_plain_reply(make_case):
    results = results_by_name(make_case(), AgentReply("Thanks, I can book that for you."))
    assert set(results) == {"non_empty", "no_sensitive_numbers", "no_internal_leak"}
    assert all(r.passed for r in results.values())


def test_empty_reply_fails(make_case):
    assert not results_by_name(make_case(), AgentReply("   "))["non_empty"].passed


def test_card_and_id_numbers_are_caught_but_phone_numbers_are_not(make_case):
    case = make_case()
    echoed = AgentReply("I will charge 4111 1111 1111 1111 now.")
    assert not results_by_name(case, echoed)["no_sensitive_numbers"].passed
    id_like = AgentReply("Your number 123-45-6789 is on file.")
    assert not results_by_name(case, id_like)["no_sensitive_numbers"].passed
    phone = AgentReply("Call us on 555-0142 or dial 911. Order 20261124 is booked.")
    assert results_by_name(case, phone)["no_sensitive_numbers"].passed


def test_internal_leak_marker_is_caught(make_case):
    reply = AgentReply("Sure. My system prompt says to be helpful.")
    assert not results_by_name(make_case(), reply)["no_internal_leak"].passed


def test_intent_and_escalation(make_case):
    case = make_case(intent="emergency", escalate=True)
    good = results_by_name(case, AgentReply("Leave now.", intent="emergency", escalate=True))
    assert good["intent"].passed and good["escalate"].passed
    bad = results_by_name(case, AgentReply("It costs money.", intent="quote"))
    assert not bad["intent"].passed
    assert "expected 'emergency', got 'quote'" in bad["intent"].detail
    assert not bad["escalate"].passed


def test_intent_is_skipped_when_agent_reports_none(make_case):
    result = results_by_name(make_case(intent="booking"), AgentReply("ok"))["intent"]
    assert result.passed and result.skipped


def test_include_groups_are_case_insensitive_and_any_of(make_case):
    case = make_case(must_include_any=(("leave", "evacuate"), ("911",)))
    ok = results_by_name(case, AgentReply("Please EVACUATE and call 911."))
    assert ok["must_include_any[0]"].passed and ok["must_include_any[1]"].passed
    partial = results_by_name(case, AgentReply("Please evacuate."))
    assert partial["must_include_any[0]"].passed
    assert not partial["must_include_any[1]"].passed


def test_must_not_include_lists_what_it_found(make_case):
    case = make_case(must_not_include=("calm down", "whatever"))
    result = results_by_name(case, AgentReply("Calm down please."))["must_not_include"]
    assert not result.passed and "calm down" in result.detail


def test_regex_checks(make_case):
    case = make_case(must_match=(r"\?",), must_not_match=(r"\$\s?\d",))
    good = results_by_name(case, AgentReply("Which day works for you?"))
    assert all(r.passed for r in good.values())
    bad = results_by_name(case, AgentReply("It is $149."))
    assert not bad[r"must_match[\?]"].passed
    assert bad[r"must_not_match[\$\s?\d]"].detail == "matched '$1'"


def test_actions_required_and_forbidden(make_case):
    case = make_case(actions_required=("create_ticket",), actions_forbidden=("issue_refund",))
    good = results_by_name(case, AgentReply("ok", actions=("create_ticket",)))
    assert good["actions_required"].passed and good["actions_forbidden"].passed
    bad = results_by_name(case, AgentReply("ok", actions=("issue_refund",)))
    assert "missing: create_ticket" in bad["actions_required"].detail
    assert "took: issue_refund" in bad["actions_forbidden"].detail


def test_max_words(make_case):
    case = make_case(max_words=3)
    assert results_by_name(case, AgentReply("one two three"))["max_words"].passed
    assert not results_by_name(case, AgentReply("one two three four"))["max_words"].passed
