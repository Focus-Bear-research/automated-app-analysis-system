# Issue #25 – how well Jev agrees with the test-set labels

Model: `jev-1.14.0`. Each run compares Jev's theme with the label in the test set.

| Run | Date | Reviews | % agreement | Cohen's kappa | Median confidence: agrees / disagrees |
|---|---|---|---|---|---|
| v1 descriptions, all apps | 22 Oct 2026 | 100 | 72% | 0.65 | 0.99 / 0.62 |
| v2 descriptions, all apps | 22 Oct 2026 | 100 | 82% | 0.77 | 0.98 / 0.75 |
| v2 descriptions, competitor apps only | 29 Oct 2026 | 36 | 94% | 0.93 | 0.99 / 0.71 |

Kappa guide: 0.6–0.8 good, above 0.8 very good.

## What changed between v1 and v2
All 28 v1 disagreements were reviewed (`issue25_disagreement_review.csv`). The main problem was broken apps being labelled `too_rigid`, so the theme descriptions in `etl/complaint_themes.py` were made clearer.

## How far to trust these numbers
- The descriptions were improved using the same reviews they were then tested on, so v2 is likely a bit optimistic.
- The competitor-only run has just 36 reviews, and some themes have only 1 or 2.
- A fresh test set is needed to confirm the result.

## Files
- `issue25_test_set.csv`: the current 36 competitor reviews; `issue25_test_set_v1_all_apps.csv`: the original 100
- `issue25_jev_results.csv`: Jev's v2 answers; `issue25_jev_results_v1.csv`: Jev's v1 answers
- `issue25_disagreements.csv`: the 2 disagreements in the competitor-only run
