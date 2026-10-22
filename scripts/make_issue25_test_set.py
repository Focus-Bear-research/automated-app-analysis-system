# scripts/make_issue25_test_set.py
# =====================================================================
# Make a test set of bad reviews to label by hand   (issue #25)
# =====================================================================
# WHAT IS THIS FOR?
#   Before we let Jev (the AI) sort reviews into complaint themes, a
#   human labels a small set first. Later we run Jev on the SAME reviews
#   and compare: if Jev mostly agrees with the human, we can trust it on
#   all the other reviews. Your labels are the "answer key".
#
# HOW TO RUN IT (from the project folder):
#   .venv/bin/python scripts/make_issue25_test_set.py
#   .venv/bin/python scripts/make_issue25_test_set.py --n 50     # a different size
#
# SAFE: it never overwrites a test set you've already started labelling,
# unless you add --force.
# =====================================================================

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------
# Work out the project folder from where THIS file is, so the script
# works no matter which folder you run it from.
#   __file__            = .../automated-app-analysis-system/scripts/make_issue25_test_set.py
#   .parents[1]         = .../automated-app-analysis-system
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Same idea as app.py: you can point the script at other data with the
# CURATED_DIR environment variable. Normally it's data/curated.
CURATED_DIR = Path(os.environ.get("CURATED_DIR", PROJECT_ROOT / "data" / "curated"))

REVIEWS_CSV = CURATED_DIR / "reviews.csv"
OUT_CSV = PROJECT_ROOT / "data" / "labels" / "issue25_test_set.csv"

# The themes you choose from when labelling (agreed with Jeremy, 22 Oct).
THEMES = [
    "pricing",
    "bugs_crashes",
    "too_easy_to_bypass",
    "too_rigid",
    "notifications",
    "onboarding",
    "sync",
    "missing_feature",
    "other",
]

# A fixed "seed" makes the random pick the same every time you run it.
# 42 is just a habit; any number works, but don't change it later.
RANDOM_SEED = 42


def main():
    # -----------------------------------------------------------------
    # 1. Read the options typed after the script name
    # -----------------------------------------------------------------
    parser = argparse.ArgumentParser(description="Make a hand-labelling test set for issue #25.")
    parser.add_argument("--n", type=int, default=100, help="how many reviews to pick (default 100)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing test set")
    args = parser.parse_args()

    # -----------------------------------------------------------------
    # 2. Don't destroy hand labels by accident
    # -----------------------------------------------------------------
    # Labelling takes an hour or two. If the file is already there, stop,
    # so running the script again can't wipe your work.
    if OUT_CSV.exists() and not args.force:
        sys.exit(f"{OUT_CSV} already exists. Not overwriting your labels. "
                 f"Use --force if you really want a new one.")

    # -----------------------------------------------------------------
    # 3. Load the reviews
    # -----------------------------------------------------------------
    if not REVIEWS_CSV.exists():
        sys.exit(f"Can't find {REVIEWS_CSV}. Run the pipeline first (scripts/refresh_all.py).")

    reviews = pd.read_csv(REVIEWS_CSV)
    print(f"Loaded {len(reviews):,} reviews from {REVIEWS_CSV}")

    # Stop with a clear message if a column we need is missing, instead
    # of guessing another column (that was problem #9 in the old PR).
    needed = ["review_id", "app_key", "store", "rating", "body"]
    missing = [col for col in needed if col not in reviews.columns]
    if missing:
        sys.exit(f"reviews.csv is missing these columns: {missing}")

    # -----------------------------------------------------------------
    # 4. Keep only the bad reviews (1 or 2 stars)
    # -----------------------------------------------------------------
    bad = reviews[reviews["rating"] <= 2].copy()

    # Drop reviews with no text. There's nothing to label in them.
    bad["body"] = bad["body"].fillna("").str.strip()
    bad = bad[bad["body"] != ""]
    print(f"Bad reviews (1-2 stars) with text: {len(bad):,}")

    # -----------------------------------------------------------------
    # 5. Remove duplicates
    # -----------------------------------------------------------------
    # The same review can appear more than once: once per country it was
    # scraped from (same review_id), or copy-pasted text (same body).
    # We only want each review once, or we'd label the same thing twice.
    before = len(bad)
    bad = bad.drop_duplicates(subset="review_id")
    bad = bad.drop_duplicates(subset="body")
    print(f"Removed {before - len(bad):,} duplicates, {len(bad):,} left")

    if len(bad) < args.n:
        sys.exit(f"Only {len(bad)} reviews left, but you asked for {args.n}.")

    # -----------------------------------------------------------------
    # 6. Pick the test set at random
    # -----------------------------------------------------------------
    sample = bad.sample(n=args.n, random_state=RANDOM_SEED)

    # Keep only the columns you need for labelling, and add two empty
    # ones for you to fill in.
    sample = sample[["review_id", "app_key", "store", "rating", "body"]]
    sample["my_label"] = ""   # one theme from THEMES
    sample["notes"] = ""      # second theme, or what an "other" review is about

    # -----------------------------------------------------------------
    # 7. Save it
    # -----------------------------------------------------------------
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)   # make data/labels/ if it isn't there
    sample.to_csv(OUT_CSV, index=False)

    print()
    print(f"Saved {len(sample)} reviews from {sample['app_key'].nunique()} apps to {OUT_CSV}")
    print("Most common apps in the sample:")
    print(sample["app_key"].value_counts().head(5).to_string())
    print()
    print("Next: open the file and fill in my_label with one of:")
    print("  " + ", ".join(THEMES))


if __name__ == "__main__":
    main()
