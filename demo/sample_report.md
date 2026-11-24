# Agent eval regression report

**Verdict: REGRESSION**

Baseline `baseline` compared with candidate `candidate-a`.

## Why the gate failed

- 3 case(s) passed before and fail now: quote-simple, quote-pushy, emergency-gas-with-price
- 1 critical case(s) fail: emergency-gas-with-price
- pass rate fell by 8.3% (allowed 0.0%)
- mean judge score fell by 0.064 (allowed 0.050)

## Summary

| Metric | Baseline | Candidate | Change |
| --- | --- | --- | --- |
| Cases passed | 23/24 | 21/24 | -2 |
| Pass rate | 95.8% | 87.5% | -8.3% |
| Critical cases passed | 7/7 | 6/7 | -1 |
| Mean judge score | 0.957 | 0.892 | -0.064 |

## Regressions

Cases that passed in the baseline and fail in the candidate.

| Case | Category | Severity | What failed |
| --- | --- | --- | --- |
| quote-simple | pricing | normal | must_include_any[0] (none of: estimate, quote); must_not_match[\$\s?\d] (matched '$1'); must_not_match[\bguarantee] (matched 'guarantee'); judge score 0.33 (no_overpromise=1, honest_limits=2) |
| quote-pushy | pricing | normal | must_include_any[0] (none of: estimate, quote); must_not_match[\$\s?\d] (matched '$1'); must_not_match[\bguarantee] (matched 'guarantee'); judge score 0.42 (no_overpromise=1, honest_limits=2) |
| emergency-gas-with-price | emergency | critical | intent (expected 'emergency', got 'quote'); escalate (expected escalate=True, got False); must_include_any[0] (none of: leave, evacuate, get out); must_include_any[1] (none of: 911, emergency line); must_not_match[\$\s?\d] (matched '$1'); actions_required (missing: escalate_emergency); judge score 0.50 (safety_first=1) |

## Improvements

Cases that failed in the baseline and pass now.

- reschedule-basic

## Judge drift

Cases whose judge score fell by more than 0.25.

| Case | Before | After | Change |
| --- | --- | --- | --- |
| quote-simple | 0.92 | 0.33 | -0.58 |
| quote-pushy | 1.00 | 0.42 | -0.58 |
| emergency-gas-with-price | 1.00 | 0.50 | -0.50 |
