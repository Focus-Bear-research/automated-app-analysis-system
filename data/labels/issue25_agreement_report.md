# Issue #25 – Jev vs test-set labels

_Run on 29 Oct 2026 · model `jev-1.14.0` · 36 reviews_

## Headline

| Measure | Value |
|---|---|
| % agreement | 94% (34 of 36) |
| Cohen's kappa | 0.93 |
| Median Jev confidence when it agrees | 0.99 |
| Median Jev confidence when it disagrees | 0.71 |

Kappa guide: 0.6–0.8 good, above 0.8 very good.

## Agreement per theme (by test-set label)

| my_label | my_reviews | jev_agrees | agreement |
|---|---|---|---|
| pricing | 13 | 13 | 1.0 |
| bugs_crashes | 8 | 7 | 0.88 |
| other | 7 | 7 | 1.0 |
| onboarding | 2 | 2 | 1.0 |
| sync | 2 | 2 | 1.0 |
| too_easy_to_bypass | 2 | 2 | 1.0 |
| missing_feature | 1 | 0 | 0.0 |
| too_rigid | 1 | 1 | 1.0 |

## Confusion table (rows = test-set label, columns = Jev)

| my_label | bugs_crashes | onboarding | other | pricing | sync | too_easy_to_bypass | too_rigid |
|---|---|---|---|---|---|---|---|
| bugs_crashes | 7 | 0 | 0 | 0 | 0 | 0 | 1 |
| missing_feature | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| onboarding | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| other | 0 | 0 | 7 | 0 | 0 | 0 | 0 |
| pricing | 0 | 0 | 0 | 13 | 0 | 0 | 0 |
| sync | 0 | 0 | 0 | 0 | 2 | 0 | 0 |
| too_easy_to_bypass | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| too_rigid | 0 | 0 | 0 | 0 | 0 | 0 | 1 |

All 2 disagreements are in `issue25_disagreements.csv`, most confident first.
