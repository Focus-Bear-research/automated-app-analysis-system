# Issue #25 – Jev vs test-set labels

_Run on 22 Oct 2026 · model `jev-1.14.0` · 100 reviews_

## Headline

| Measure | Value |
|---|---|
| % agreement | 82% (82 of 100) |
| Cohen's kappa | 0.77 |
| Median Jev confidence when it agrees | 0.98 |
| Median Jev confidence when it disagrees | 0.75 |

Kappa guide: 0.6–0.8 good, above 0.8 very good.

## Agreement per theme (by test-set label)

| my_label | my_reviews | jev_agrees | agreement |
|---|---|---|---|
| other | 28 | 19 | 0.68 |
| bugs_crashes | 25 | 19 | 0.76 |
| pricing | 25 | 25 | 1.0 |
| too_rigid | 6 | 6 | 1.0 |
| onboarding | 5 | 4 | 0.8 |
| sync | 5 | 5 | 1.0 |
| missing_feature | 4 | 2 | 0.5 |
| too_easy_to_bypass | 2 | 2 | 1.0 |

## Confusion table (rows = test-set label, columns = Jev)

| my_label | bugs_crashes | missing_feature | onboarding | other | pricing | sync | too_easy_to_bypass | too_rigid |
|---|---|---|---|---|---|---|---|---|
| bugs_crashes | 19 | 0 | 0 | 2 | 1 | 0 | 0 | 3 |
| missing_feature | 0 | 2 | 0 | 1 | 1 | 0 | 0 | 0 |
| onboarding | 1 | 0 | 4 | 0 | 0 | 0 | 0 | 0 |
| other | 2 | 0 | 1 | 19 | 1 | 1 | 1 | 3 |
| pricing | 0 | 0 | 0 | 0 | 25 | 0 | 0 | 0 |
| sync | 0 | 0 | 0 | 0 | 0 | 5 | 0 | 0 |
| too_easy_to_bypass | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| too_rigid | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 6 |

All 18 disagreements are in `issue25_disagreements.csv`, most confident first.
