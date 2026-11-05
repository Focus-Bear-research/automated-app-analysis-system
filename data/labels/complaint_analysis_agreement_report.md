# Complaint analysis – how well Jev agrees with the test-set labels

Model: `jev-1.14.0`. Each run compares Jev's theme with the label in the test set.

| Run | Date | Reviews | % agreement | Cohen's kappa | Median confidence: agrees / disagrees |
|---|---|---|---|---|---|
| v1 descriptions, all apps | 22 Oct 2026 | 100 | 72% | 0.65 | 0.99 / 0.62 |
| v2 descriptions, all apps | 22 Oct 2026 | 100 | 82% | 0.77 | 0.98 / 0.75 |
| v2 descriptions, competitor apps only (current) | 29 Oct 2026 | 36 | 94% | 0.93 | 0.99 / 0.71 |

Kappa guide: 0.6–0.8 good, above 0.8 very good.

## What changed between v1 and v2
All 28 v1 disagreements were reviewed. The main problem was broken apps being labelled `too_rigid`, so the theme descriptions in `etl/complaint_themes.py` were made clearer.

## How far to trust these numbers
- The descriptions were improved using the same reviews they were then tested on, so v2 is likely a bit optimistic.
- The competitor-only run has just 36 reviews, and some themes have only 1 or 2.
- A fresh test set is needed to confirm the result.

## Files
- `complaint_analysis_test_set.csv`: the current 36 competitor reviews and their labels
- `make_complaint_analysis_test_set.py`: makes a new test set to label
- `scripts/compare_jev_test_set.py`: runs Jev on the test set and measures agreement. It needs a Jev key and writes two local files (Jev's answers and the disagreements), which git ignores
