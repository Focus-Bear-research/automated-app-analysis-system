## Project Resources

- [(Original) ReadMe](docs/ReadMe.pdf)
- [Research Paper](docs/ResearchPaper(dspg).pdf)
- [Workflow Diagram](docs/WorkflowDiagram.drawio.png)
- Ulrik Lynggs article: https://www.sciencedirect.com/science/article/pii/S1071581922000957?via%3Dihub

## Review dataset

The full review set now lives in this repo at `data/curated/reviews.csv.gz`
(67 MB), stored with Git LFS. You need git-lfs installed to get the real file —
without it git hands you a small text pointer instead:

    git lfs install
    git lfs pull

Read it directly, no need to decompress:

    import pandas as pd
    df = pd.read_csv('data/curated/reviews.csv.gz')

To skip the 67 MB download when cloning:

    GIT_LFS_SKIP_SMUDGE=1 git clone <url>

| file | rows | what it is |
|---|---|---|
| `data/curated/reviews.csv.gz` | 801,001 | every unique Play/Chrome review collected, `special_reviews` marks the neurodivergent ones |
| `data/curated/ios_reviews.csv` | 129,077 | the iOS scrape, 74 apps across 18 countries |

That is 6,186 neurodivergent reviews out of 801,001 in the gzipped set (0.77%).
Counting the iOS file as well, the verified total is **9,151 neurodivergent
reviews out of 921,506 unique reviews** (0.99%), against a target of 5,000.

Confirm the first number straight from the file:

    python -c "import pandas as pd; d=pd.read_csv('data/curated/reviews.csv.gz'); print(len(d), (d['special_reviews']==True).sum())"

For the combined 9,151, run `python verify_nd_count.py` and then
`python audit_nd_count.py` — note those read the individual per-scrape files,
which are not in the repo, so they reproduce the number only on a machine that
ran the scrapes.

`data/curated/reviews.csv` is still the old 112,638-row subset carrying 2,210
flagged reviews, and the dashboard reports whatever is in that file. To make the
dashboard show the real count, run `python build_dashboard_reviews.py` after
pulling LFS.

Mirror, in case the repo's LFS quota is exhausted:
https://drive.google.com/drive/folders/1kWmwiv46hKgQQPOsPm71tQ3frs5N1hAy?usp=sharing

## Scraping notes

`scrapers/reviews_pipeline.py` retries a fetch that errors or comes back empty
before it gives up on an app, and ends every run with a `[SUMMARY]` line saying
how many fetches actually completed. If any were skipped it writes them to
`data/curated/skipped_fetches.csv` and says the scrape is incomplete, so re-run
those apps before treating the data as finished.

`--since-days` defaults to 0, which keeps every review. Passing a positive
value silently discards anything older than that, so only use it on purpose.
