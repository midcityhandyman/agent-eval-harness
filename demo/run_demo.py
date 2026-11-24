"""Offline demo: one baseline, two candidate agents, one gate.

Runs with the standard library only. No network, no keys.

    python demo/run_demo.py

It drives the same CLI entry point the CI workflow uses and exits 0 only when
the gate rejects the regressed agent and accepts the improved one.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evalharness.cli import main  # noqa: E402

GOLDEN = "golden/golden_set.jsonl"
BASELINE = "baselines/baseline.json"
WORK = "runs/demo"
AGENTS = "evalharness.sample_agents"


def step(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def cli(*args: str) -> int:
    print("$ evalharness " + " ".join(args))
    sys.stdout.flush()
    code = main(list(args))
    print(f"[exit code {code}]")
    return code


def run_demo() -> int:
    os.chdir(ROOT)  # relative paths keep the output identical on every machine

    step("1. Validate the golden set")
    cli("validate", "--golden", GOLDEN)

    step("2. The committed baseline (recorded from the stable agent)")
    print(f"{BASELINE} is what every candidate is compared against.")
    print("The stable agent has one known gap: it books a new visit when asked to reschedule.")

    step("3. Candidate A: a 'sales friendly' change that quotes prices up front")
    cli("run", "--golden", GOLDEN, "--agent", f"{AGENTS}:regressed_agent", "--judge", "mock",
        "--label", "candidate-a", "--out", f"{WORK}/candidate-a.json")

    step("4. Gate candidate A against the baseline")
    code_a = cli("compare", BASELINE, f"{WORK}/candidate-a.json",
                 "--report", "demo/sample_report.md")

    step("5. Candidate B: only the reschedule fix")
    cli("run", "--golden", GOLDEN, "--agent", f"{AGENTS}:improved_agent", "--judge", "mock",
        "--label", "candidate-b", "--out", f"{WORK}/candidate-b.json")

    step("6. Gate candidate B against the baseline")
    code_b = cli("compare", BASELINE, f"{WORK}/candidate-b.json")

    shutil.rmtree(WORK, ignore_errors=True)

    step("Result")
    print(f"candidate A (regressed): gate exit code {code_a} -> " + ("blocked" if code_a else "MERGED"))
    print(f"candidate B (improved) : gate exit code {code_b} -> " + ("BLOCKED" if code_b else "allowed"))
    ok = code_a == 1 and code_b == 0
    print("Demo " + ("passed: the gate blocked the regression and allowed the fix." if ok else "FAILED."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run_demo())
