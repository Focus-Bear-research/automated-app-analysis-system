# scripts/analyze_competitor_complaints.py
# =====================================================================
# Why do users leave competitors?   (issue #25)
# =====================================================================
# WHAT IT DOES:
#   1. Takes the bad reviews (1-2 stars) of Focus Bear's competitors.
#      Reviews with no app_key and non-competitor apps are removed first
#      (etl/review_filters.py, list in scrapers/seeds.yml).
#   2. Asks Jev (TypeSafe AI) for each review's MAIN complaint theme
#      (themes in etl/complaint_themes.py).
#   3. Adds up, per app, how many bad reviews fall in each theme and what
#      share of that app's bad reviews that is, with example quotes.
#
# HOW TO RUN IT (from the project folder, in a terminal where you've set
# the key with `read -s` + `export TYPESAFE_API_KEY`):
#   .venv/bin/python scripts/analyze_competitor_complaints.py --limit 200   # cheap test first
#   .venv/bin/python scripts/analyze_competitor_complaints.py               # all reviews
#   .venv/bin/python scripts/analyze_competitor_complaints.py --summary-only  # re-count, no Jev calls
#
# IT CAN BE STOPPED AND RESTARTED: every answer is saved to the labels
# file, and a re-run only asks Jev about reviews it hasn't answered yet.
#
# OUTPUT (in data/curated/, or CURATED_DIR if set):
#   competitor_complaint_labels.csv   one row per review: Jev's theme + confidence
#   competitor_complaints_summary.csv one row per app + theme: counts, share, quotes
#
# COST: about 700 tokens per review (~8,000 reviews -> ~5.6M tokens).
# =====================================================================

import argparse
import asyncio
import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Let this script import from the project's own folders (e.g. etl/).
sys.path.insert(0, str(PROJECT_ROOT))
from etl.complaint_themes import JEV_MODEL, MIN_CONFIDENCE, QUESTION  # noqa: E402
from etl.review_filters import filter_reviews  # noqa: E402

from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeError  # noqa: E402

CURATED_DIR = Path(os.environ.get("CURATED_DIR", PROJECT_ROOT / "data" / "curated"))
REVIEWS_CSV = CURATED_DIR / "reviews.csv"
APP_CARDS_CSV = CURATED_DIR / "app_cards.csv"              # only used for app names
LABELS_CSV = CURATED_DIR / "competitor_complaint_labels.csv"
SUMMARY_CSV = CURATED_DIR / "competitor_complaints_summary.csv"

QUOTES_PER_THEME = 3   # example quotes kept per app + theme
SAVE_EVERY = 100       # write answers to disk after this many new ones


# ---------------------------------------------------------------------
# 1. Which reviews to analyse
# ---------------------------------------------------------------------
def load_bad_competitor_reviews() -> pd.DataFrame:
    """Bad reviews of competitor apps, one row per unique review."""
    if not REVIEWS_CSV.exists():
        sys.exit(f"Can't find {REVIEWS_CSV}. Run the pipeline first (scripts/refresh_all.py).")

    reviews = pd.read_csv(REVIEWS_CSV, dtype={"review_id": str}, low_memory=False)
    needed = ["review_id", "app_key", "rating", "body"]
    missing = [c for c in needed if c not in reviews.columns]
    if missing:
        sys.exit(f"reviews.csv is missing these columns: {missing}")

    # Jeremy's clean-ups: no app_key -> removed; non-competitors -> removed.
    reviews = filter_reviews(reviews)

    bad = reviews[reviews["rating"] <= 2].copy()
    bad["body"] = bad["body"].fillna("").astype(str).str.strip()
    bad = bad[bad["body"] != ""]                      # nothing to classify without text

    # The same review can be scraped once per country (same review_id),
    # and some text is copy-pasted (same app + body). Keep each once.
    bad = bad.drop_duplicates(subset="review_id")
    bad = bad.drop_duplicates(subset=["app_key", "body"])
    print(f"Bad competitor reviews to classify: {len(bad):,} from {bad['app_key'].nunique()} apps")
    return bad[["review_id", "app_key", "rating", "body"]]


# ---------------------------------------------------------------------
# 2. Ask Jev (many reviews at the same time)
# ---------------------------------------------------------------------
def load_saved_labels() -> pd.DataFrame:
    """Answers from earlier runs (the cache). Empty table if there are none."""
    if LABELS_CSV.exists():
        return pd.read_csv(LABELS_CSV, dtype={"review_id": str})
    return pd.DataFrame(columns=["review_id", "jev_label", "jev_confidence", "jev_model"])


async def classify(todo: pd.DataFrame, saved: pd.DataFrame, concurrency: int) -> pd.DataFrame:
    """Send every review in `todo` to Jev. Saves progress as it goes."""
    new_rows: list[dict] = []
    # A semaphore lets at most `concurrency` requests run at the same time,
    # so ~8,000 reviews take minutes instead of hours, without flooding Jev.
    limit = asyncio.Semaphore(concurrency)
    failed: list[str] = []

    def save() -> pd.DataFrame:
        # On the first run `saved` is empty; leave it out so pandas doesn't warn.
        parts = [p for p in (saved, pd.DataFrame(new_rows)) if not p.empty]
        all_rows = pd.concat(parts, ignore_index=True) if parts else saved
        all_rows.to_csv(LABELS_CSV, index=False)
        return all_rows

    # Retry short network hiccups and rate limits a few times before giving up.
    retry = RetryPolicy(max_retries=4, backoff_initial=1.0, backoff_max=20.0)

    async with AsyncTypeSafeClient(model=JEV_MODEL, retry=retry) as client:

        async def one(review_id: str, body: str):
            async with limit:
                try:
                    response = await client.system_one(
                        state={"review": body},
                        questions={"theme": QUESTION},
                    )
                except TypeSafeError as e:
                    # Don't stop the whole run for one review: note it and
                    # move on. A re-run will try it again.
                    failed.append(review_id)
                    print(f"  ! Jev error on {review_id}: {e}")
                    return
                answer = response.choices["theme"]
                new_rows.append({
                    "review_id": review_id,
                    "jev_label": answer.choice,
                    "jev_confidence": round(answer.confidence, 3),
                    "jev_model": response.model,
                })
                if len(new_rows) % SAVE_EVERY == 0:
                    save()
                    print(f"  {len(new_rows):,}/{len(todo):,} done")

        await asyncio.gather(*(one(r.review_id, r.body) for r in todo.itertuples(index=False)))

    all_rows = save()
    print(f"Classified {len(new_rows):,} reviews this run.")
    if failed:
        print(f"{len(failed)} reviews failed; run the script again to retry them.")
    return all_rows


# ---------------------------------------------------------------------
# 3. Add up per app and theme
# ---------------------------------------------------------------------
def app_names() -> dict[str, str]:
    """app_key -> app name, where we have one (falls back to the app_key)."""
    if not APP_CARDS_CSV.exists():
        return {}
    cards = pd.read_csv(APP_CARDS_CSV, usecols=["app_key", "title"]).dropna()
    return dict(zip(cards["app_key"], cards["title"]))


def summarise(bad: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    df = bad.merge(labels, on="review_id", how="inner")
    if df.empty:
        sys.exit("No classified reviews yet. Run without --summary-only first.")

    # Low-confidence answers are kept, but under their own "uncertain"
    # theme, so they don't quietly inflate any real theme.
    df["theme"] = df["jev_label"].where(df["jev_confidence"] >= MIN_CONFIDENCE, "uncertain")

    names = app_names()
    rows = []
    for app_key, app_df in df.groupby("app_key"):
        app_total = len(app_df)
        for theme, t_df in app_df.groupby("theme"):
            # Best example quotes: the reviews Jev was most sure about,
            # shortened so the dashboard stays readable.
            top = t_df.sort_values("jev_confidence", ascending=False).head(QUOTES_PER_THEME)
            quotes = [b if len(b) <= 300 else b[:297] + "..." for b in top["body"]]
            rows.append({
                "app_key": app_key,
                "app_name": names.get(app_key, app_key),
                "theme": theme,
                "n_reviews": len(t_df),
                "app_bad_reviews": app_total,
                # share = this theme's part of the app's bad reviews (problem #6
                # in the old PR: raw counts can't be compared between apps).
                "share": round(len(t_df) / app_total, 3),
                "example_quotes": " || ".join(quotes),
            })
    summary = pd.DataFrame(rows).sort_values(["app_key", "n_reviews"], ascending=[True, False])
    summary.to_csv(SUMMARY_CSV, index=False)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Classify competitor complaints with Jev (issue #25).")
    parser.add_argument("--limit", type=int, default=None,
                        help="only classify this many new reviews (cheap test run)")
    parser.add_argument("--concurrency", type=int, default=10,
                        help="how many Jev requests run at the same time (default 10)")
    parser.add_argument("--summary-only", action="store_true",
                        help="don't call Jev; just rebuild the summary from saved answers")
    args = parser.parse_args()

    bad = load_bad_competitor_reviews()
    labels = load_saved_labels()

    if not args.summary_only:
        todo = bad[~bad["review_id"].isin(labels["review_id"])]
        if args.limit is not None:
            todo = todo.sample(n=min(args.limit, len(todo)), random_state=42)
        print(f"{len(labels):,} already classified, {len(todo):,} to send to Jev now.")
        if len(todo):
            if not os.environ.get("TYPESAFE_API_KEY"):
                sys.exit("TYPESAFE_API_KEY isn't set in this terminal. Run the `read -s` and `export` steps first.")
            labels = asyncio.run(classify(todo, labels, args.concurrency))

    summary = summarise(bad, labels)

    # Short market-wide overview in the terminal.
    done = bad.merge(labels, on="review_id")
    overall = (summary.groupby("theme")["n_reviews"].sum()
               .sort_values(ascending=False))
    print()
    print(f"Themes across {summary['app_key'].nunique()} apps "
          f"({len(done):,} of {len(bad):,} bad reviews classified):")
    for theme, n in overall.items():
        print(f"  {theme:<20} {n:>6,}  {n / overall.sum():.0%}")
    print()
    print(f"Saved: {LABELS_CSV}")
    print(f"       {SUMMARY_CSV}")


if __name__ == "__main__":
    main()
