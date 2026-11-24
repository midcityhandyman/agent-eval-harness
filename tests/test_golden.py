import json

import pytest

from evalharness.golden import GoldenSetError, golden_hash, load_golden, parse_cases
from evalharness.rubric import CRITERIA


def test_repo_golden_set_is_valid_and_covers_the_basics(golden_cases):
    assert len(golden_cases) >= 20
    assert len({c.id for c in golden_cases}) == len(golden_cases)
    categories = {c.category for c in golden_cases}
    assert {"booking", "emergency", "complaint", "billing", "safety"} <= categories
    assert sum(1 for c in golden_cases if c.severity == "critical") >= 5
    for case in golden_cases:
        assert case.rubric, f"{case.id} has no rubric"
        assert set(case.rubric) <= set(CRITERIA)


def test_golden_set_uses_only_placeholder_contact_data(golden_cases):
    surnames = {"Sample", "Example", "Placeholder", "Testcase", "Demo", "Fixture"}
    for case in golden_cases:
        assert case.customer_name.split()[-1] in surnames
        assert "@" not in case.message


def test_parse_reports_every_problem_at_once():
    records = [
        {"id": "ok-case", "category": "x", "message": "hello"},
        {"id": "ok-case", "category": "x", "message": "hello again"},
        {"id": "Bad Id", "category": "x", "message": "hi"},
        {"id": "bad-regex", "category": "x", "message": "hi", "expect": {"must_match": ["("]}},
        {"id": "bad-rubric", "category": "x", "message": "hi", "rubric": ["charisma"]},
        {"id": "bad-key", "category": "x", "message": "hi", "expect": {"must_inclde": []}},
        {"id": "bad-sev", "category": "x", "message": "hi", "severity": "urgent"},
        {"id": "no-message", "category": "x"},
    ]
    with pytest.raises(GoldenSetError) as info:
        parse_cases(records)
    text = "\n".join(info.value.problems)
    assert "duplicate id" in text
    assert "lowercase letters" in text
    assert "invalid regex" in text
    assert "unknown rubric criterion 'charisma'" in text
    assert "unknown expect key 'must_inclde'" in text
    assert "severity must be one of" in text
    assert "'message' is required" in text


def test_load_reports_bad_json_line_number(tmp_path):
    path = tmp_path / "set.jsonl"
    path.write_text('{"id": "a", "category": "x", "message": "hi"}\n{not json}\n', encoding="utf-8")
    with pytest.raises(GoldenSetError) as info:
        load_golden(path)
    assert "line 2" in info.value.problems[0]


def test_empty_set_is_rejected(tmp_path):
    path = tmp_path / "set.jsonl"
    path.write_text("# only a comment\n", encoding="utf-8")
    with pytest.raises(GoldenSetError):
        load_golden(path)


def test_hash_changes_when_an_expectation_changes(tmp_path):
    record = {"id": "a", "category": "x", "message": "hi", "expect": {"max_words": 10}}
    first = parse_cases([record])
    record["expect"]["max_words"] = 11
    second = parse_cases([json.loads(json.dumps(record))])
    assert golden_hash(first) != golden_hash(second)
    assert golden_hash(first) == golden_hash(first)
