# data/labels/make_issue31_test_set.py
# =====================================================================
# Make a foreign-language test set to label by hand   (issue #31)
# =====================================================================
# WHAT IS THIS FOR?
#   We want to know if Jev works on reviews that aren't in English.
#   Like in #25, a human labels a small set first, then we run Jev on the
#   SAME reviews and compare. Your labels are the "answer key".
#
# WHAT IT PICKS, for each language (German, Portuguese, French, Spanish,
# Japanese):
#   - 20 bad reviews (1-2 stars): you label the theme AND the sentiment
#   - 10 other reviews (3-5 stars): you label the sentiment only
#   The 3-5 star reviews are there because a test made of only bad
#   reviews can't show whether Jev recognises a positive one.
#
# HOW TO RUN IT (from the project folder):
#   .venv/bin/python data/labels/make_issue31_test_set.py
#
# SAFE: it never overwrites a test set you've already started labelling,
# unless you add --force.
# =====================================================================

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from langdetect import DetectorFactory, LangDetectException, detect

# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Let this script import from the project's own folders (e.g. etl/).
sys.path.insert(0, str(PROJECT_ROOT))
from etl.review_filters import filter_reviews  # noqa: E402  (issue #25: no app_key / excluded apps)

CURATED_DIR = Path(os.environ.get("CURATED_DIR", PROJECT_ROOT / "data" / "curated"))

# ios_reviews.csv, not reviews.csv: only the iOS scrape has foreign stores.
REVIEWS_CSV = CURATED_DIR / "ios_reviews.csv"
OUT_CSV = PROJECT_ROOT / "data" / "labels" / "issue31_test_set.csv"

# Which stores to look in for each language (language code -> store countries).
# A store's country doesn't prove a review's language, so we still detect it.
LANGUAGES = {
    "de": ["de"],         # German
    "pt": ["br"],         # Portuguese
    "fr": ["fr"],         # French
    "es": ["es", "mx"],   # Spanish
    "ja": ["jp"],         # Japanese
}

N_BAD = 20     # 1-2 star reviews per language (theme + sentiment)
N_OTHER = 10   # 3-5 star reviews per language (sentiment only)

# Language detection is unreliable on very short text, so skip it.
MIN_CHARS = 15

# A fixed "seed" makes the random pick the same every time you run it.
RANDOM_SEED = 42

# langdetect uses randomness too. Fixing its seed gives the same answer
# for the same text every time.
DetectorFactory.seed = 0


def detect_language(text: str) -> str:
    """Return the language code of the text, or "" if it can't tell."""
    try:
        return detect(text)
    except LangDetectException:
        return ""


def main():
    # -----------------------------------------------------------------
    # 1. Read the options typed after the script name
    # -----------------------------------------------------------------
    parser = argparse.ArgumentParser(description="Make a foreign-language test set for issue #31.")
    parser.add_argument("--force", action="store_true", help="overwrite an existing test set")
    args = parser.parse_args()

    # -----------------------------------------------------------------
    # 2. Don't destroy hand labels by accident
    # -----------------------------------------------------------------
    if OUT_CSV.exists() and not args.force:
        sys.exit(f"{OUT_CSV} already exists. Not overwriting your labels. "
                 f"Use --force if you really want a new one.")

    # -----------------------------------------------------------------
    # 3. Load the reviews from the stores we care about
    # -----------------------------------------------------------------
    if not REVIEWS_CSV.exists():
        sys.exit(f"Can't find {REVIEWS_CSV}. Run scrapers/ios_reviews.py first.")

    reviews = pd.read_csv(REVIEWS_CSV, low_memory=False)
    print(f"Loaded {len(reviews):,} reviews from {REVIEWS_CSV}")

    reviews = filter_reviews(reviews)

    stores = [country for countries in LANGUAGES.values() for country in countries]
    reviews = reviews[reviews["country"].isin(stores)].copy()

    # Drop reviews with no text or too little text to detect.
    reviews["body"] = reviews["body"].fillna("").str.strip()
    reviews = reviews[reviews["body"].str.len() >= MIN_CHARS]

    # The same review can appear in several stores, or be copy-pasted.
    reviews = reviews.drop_duplicates(subset="review_id")
    reviews = reviews.drop_duplicates(subset="body")
    print(f"Reviews with text in these stores, without duplicates: {len(reviews):,}")

    # -----------------------------------------------------------------
    # 4. Work out each review's real language
    # -----------------------------------------------------------------
    # The `lang` column can't be used: it says "en" on every row.
    print("Detecting languages (this can take a few minutes)...")
    reviews["detected_lang"] = reviews["body"].apply(detect_language)

    # Show how many reviews in each store are really in that store's language.
    print()
    print("Reviews whose language matches their store:")
    for lang, countries in LANGUAGES.items():
        in_store = reviews[reviews["country"].isin(countries)]
        share = (in_store["detected_lang"] == lang).mean()
        english = (in_store["detected_lang"] == "en").mean()
        print(f"  {lang}  {len(in_store):>6,} reviews   {share:>4.0%} in {lang}   {english:>4.0%} in English")
    print()

    # -----------------------------------------------------------------
    # 5. Pick the test set at random, one language at a time
    # -----------------------------------------------------------------
    picked = []
    for lang, countries in LANGUAGES.items():
        pool = reviews[reviews["country"].isin(countries) & (reviews["detected_lang"] == lang)]
        bad = pool[pool["rating"] <= 2]
        other = pool[pool["rating"] >= 3]

        if len(bad) < N_BAD or len(other) < N_OTHER:
            sys.exit(f"Not enough {lang} reviews: {len(bad)} bad and {len(other)} other.")

        picked.append(bad.sample(n=N_BAD, random_state=RANDOM_SEED))
        picked.append(other.sample(n=N_OTHER, random_state=RANDOM_SEED))

    sample = pd.concat(picked, ignore_index=True)

    # Keep only the columns you need, and add empty ones to fill in.
    sample = sample[["review_id", "app_key", "country", "detected_lang", "rating", "body"]].copy()
    sample["body_en"] = ""       # English translation, to help you read it
    sample["lang_ok"] = ""       # "no" if detected_lang is wrong
    sample["my_theme"] = ""      # 1-2 star reviews only: one theme from etl/complaint_themes.py
    sample["my_sentiment"] = ""  # every review: positive, neutral or negative
    sample["notes"] = ""         # anything you weren't sure about

    # -----------------------------------------------------------------
    # 6. Save it
    # -----------------------------------------------------------------
    # utf-8-sig tells Excel the file is UTF-8, so it shows ü and 日本語 properly.
    sample.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print(f"Saved {len(sample)} reviews from {sample['app_key'].nunique()} apps to {OUT_CSV}")
    print(sample.groupby(["detected_lang", sample["rating"] <= 2]).size().to_string())


if __name__ == "__main__":
    main()
