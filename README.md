## Project Resources

- [(Original) ReadMe](docs/ReadMe.pdf)
- [Research Paper](docs/ResearchPaper(dspg).pdf)
- [Workflow Diagram](docs/WorkflowDiagram.drawio.png)
- Ulrik Lynggs article: https://www.sciencedirect.com/science/article/pii/S1071581922000957?via%3Dihub

## Review dataset

The full scraped review set is far too large for the repo, so it lives in Google Drive:

**Dataset folder:** https://drive.google.com/drive/folders/1kWmwiv46hKgQQPOsPm71tQ3frs5N1hAy?usp=sharing

| file | rows | what it is |
|---|---|---|
| `focusbear_nd_reviews_6186.csv` | 6,186 | only the neurodivergent reviews, with their category labels |
| `focusbear_all_reviews_801k.csv.gz` | 801,001 | every unique review collected (gzipped; pandas reads it directly) |
| `README.txt` | - | column descriptions and how the labelling works |

As of 30 Oct 2026 that is 6,186 neurodivergent reviews out of 801,001 unique
reviews (0.77%), against a target of 5,000. To check those numbers yourself,
run `python verify_nd_count.py` (produces the count) and then
`python audit_nd_count.py` (checks it for duplicates and category errors).

Note that `data/curated/reviews.csv` in the repo is a 112,638-row subset
carrying 2,210 flagged reviews, because GitHub rejects files over 100 MB. The
dashboard reports whatever is in that file, so to see the full 6,186 download
the dataset from the link above and run `python build_dashboard_reviews.py`.

## Scraping notes

`scrapers/reviews_pipeline.py` retries a fetch that errors or comes back empty
before it gives up on an app, and ends every run with a `[SUMMARY]` line saying
how many fetches actually completed. If any were skipped it writes them to
`data/curated/skipped_fetches.csv` and says the scrape is incomplete, so re-run
those apps before treating the data as finished.

`--since-days` defaults to 0, which keeps every review. Passing a positive
value silently discards anything older than that, so only use it on purpose.
