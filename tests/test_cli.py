import json

from conftest import BASELINE_PATH, GOLDEN_PATH

from evalharness.cli import EXIT_OK, EXIT_REGRESSION, EXIT_USAGE, main
from evalharness.runner import load_run

AGENTS = "evalharness.sample_agents"


def run_agent(tmp_path, name, label=None):
    out = tmp_path / f"{name}.json"
    code = main(["run", "--golden", str(GOLDEN_PATH), "--agent", f"{AGENTS}:{name}_agent",
                 "--judge", "mock", "--label", label or name, "--out", str(out)])
    assert code == EXIT_OK
    return out


def test_validate_ok(capsys):
    assert main(["validate", "--golden", str(GOLDEN_PATH)]) == EXIT_OK
    assert "24 cases" in capsys.readouterr().out


def test_validate_reports_problems(tmp_path, capsys):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "a", "category": "x", "message": "hi", "severity": "nope"}\n',
                   encoding="utf-8")
    assert main(["validate", "--golden", str(bad)]) == EXIT_USAGE
    assert "severity must be one of" in capsys.readouterr().err


def test_committed_baseline_matches_the_stable_agent(tmp_path):
    """If this fails, the baseline is stale: regenerate it (see README)."""
    fresh = load_run(run_agent(tmp_path, "stable", label="baseline"))
    assert fresh == load_run(BASELINE_PATH)


def test_gate_passes_for_stable_and_improved(tmp_path, capsys):
    for name in ("stable", "improved"):
        out = run_agent(tmp_path, name)
        assert main(["compare", str(BASELINE_PATH), str(out)]) == EXIT_OK
    assert "VERDICT: OK" in capsys.readouterr().out


def test_gate_fails_for_regressed_and_writes_report(tmp_path, capsys):
    out = run_agent(tmp_path, "regressed")
    report = tmp_path / "reports" / "report.md"
    code = main(["compare", str(BASELINE_PATH), str(out), "--report", str(report)])
    assert code == EXIT_REGRESSION
    assert "VERDICT: REGRESSION" in capsys.readouterr().out
    assert "emergency-gas-with-price" in report.read_text(encoding="utf-8")


def test_thresholds_cannot_wave_through_a_flipped_case(tmp_path):
    out = run_agent(tmp_path, "regressed")
    code = main(["compare", str(BASELINE_PATH), str(out), "--max-pass-rate-drop", "1",
                 "--max-judge-drop", "1", "--allow-critical-failures"])
    assert code == EXIT_REGRESSION


def test_fail_under(tmp_path):
    args = ["run", "--golden", str(GOLDEN_PATH), "--agent", f"{AGENTS}:stable_agent",
            "--out", str(tmp_path / "r.json")]
    assert main(args + ["--fail-under", "0.9"]) == EXIT_OK
    assert main(args + ["--fail-under", "0.99"]) == EXIT_REGRESSION


def test_run_from_recorded_replies(tmp_path, capsys):
    stable = json.loads(run_agent(tmp_path, "stable").read_text(encoding="utf-8"))
    replies = tmp_path / "replies.jsonl"
    replies.write_text(
        "\n".join(json.dumps({"id": c["id"], **c["reply"]}) for c in stable["cases"]) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "replayed.json"
    code = main(["run", "--golden", str(GOLDEN_PATH), "--replies", str(replies),
                 "--label", "replayed", "--out", str(out)])
    assert code == EXIT_OK
    assert main(["compare", str(BASELINE_PATH), str(out)]) == EXIT_OK


def test_bad_inputs_exit_with_usage_code(tmp_path, capsys):
    out = str(tmp_path / "r.json")
    assert main(["run", "--golden", str(GOLDEN_PATH), "--agent", "nope", "--out", out]) == EXIT_USAGE
    assert main(["compare", "missing-a.json", "missing-b.json"]) == EXIT_USAGE
    assert "error:" in capsys.readouterr().err
