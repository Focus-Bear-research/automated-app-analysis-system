# Issue #25 – Jev vs test-set labels

_Run on 22 Oct 2026 · model `jev-1.14.0` · 100 reviews_

## Headline

| Measure | Value |
|---|---|
| % agreement | 72% (72 of 100) |
| Cohen's kappa | 0.65 |
| Median Jev confidence when it agrees | 0.99 |
| Median Jev confidence when it disagrees | 0.62 |

Kappa guide: 0.6–0.8 good, above 0.8 very good.

## Agreement per theme (by test-set label)

| my_label | my_reviews | jev_agrees | agreement |
|---|---|---|---|
| other | 28 | 19 | 0.68 |
| bugs_crashes | 25 | 14 | 0.56 |
| pricing | 25 | 24 | 0.96 |
| too_rigid | 6 | 4 | 0.67 |
| onboarding | 5 | 4 | 0.8 |
| sync | 5 | 3 | 0.6 |
| missing_feature | 4 | 3 | 0.75 |
| too_easy_to_bypass | 2 | 1 | 0.5 |

## Confusion table (rows = test-set label, columns = Jev)

| my_label | bugs_crashes | missing_feature | notifications | onboarding | other | pricing | sync | too_easy_to_bypass | too_rigid |
|---|---|---|---|---|---|---|---|---|---|
| bugs_crashes | 14 | 1 | 0 | 1 | 2 | 2 | 0 | 0 | 5 |
| missing_feature | 0 | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| onboarding | 0 | 0 | 0 | 4 | 0 | 1 | 0 | 0 | 0 |
| other | 1 | 0 | 1 | 2 | 19 | 1 | 1 | 1 | 2 |
| pricing | 0 | 0 | 0 | 0 | 0 | 24 | 0 | 0 | 1 |
| sync | 0 | 0 | 0 | 1 | 0 | 0 | 3 | 0 | 1 |
| too_easy_to_bypass | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| too_rigid | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 4 |

All 28 disagreements are in `issue25_disagreements.csv`, most confident first.
