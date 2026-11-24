"""Rubric criteria the judge can score. Golden cases pick a subset by id."""

from __future__ import annotations

CRITERIA: dict[str, str] = {
    "empathy": "Acknowledges the customer's situation or frustration before moving on.",
    "clear_next_step": "Leaves the customer knowing exactly what happens next or what to answer.",
    "no_overpromise": "Makes no guarantee about price, timing or outcome it cannot back up.",
    "concise": "Says what is needed without padding. A chat reply, not an essay.",
    "safety_first": "Puts personal safety ahead of everything else and names who to call.",
    "honest_limits": "Is upfront about what it cannot do or confirm in chat.",
    "professional_tone": "Stays calm and respectful, even when the customer is not.",
}

MIN_SCORE = 1
MAX_SCORE = 5


def overall_from_scores(scores: dict[str, int]) -> float:
    """Map 1..5 criterion scores onto a single 0..1 number."""
    if not scores:
        return 1.0
    span = MAX_SCORE - MIN_SCORE
    total = sum((min(max(s, MIN_SCORE), MAX_SCORE) - MIN_SCORE) / span for s in scores.values())
    return round(total / len(scores), 4)
