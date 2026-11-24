from pathlib import Path

import pytest

from evalharness.golden import load_golden
from evalharness.models import Expectations, GoldenCase

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "golden" / "golden_set.jsonl"
BASELINE_PATH = ROOT / "baselines" / "baseline.json"


@pytest.fixture(scope="session")
def golden_cases():
    return load_golden(GOLDEN_PATH)


@pytest.fixture
def make_case():
    def _make(case_id="case-1", severity="normal", rubric=(), **expect):
        return GoldenCase(
            id=case_id,
            category="test",
            severity=severity,
            message="My sink is leaking.",
            customer_name="Alex Sample",
            expect=Expectations(**expect),
            rubric=tuple(rubric),
        )

    return _make
