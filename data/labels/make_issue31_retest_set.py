# data/labels/make_issue31_retest_set.py
# =====================================================================
# Pick NEW reviews to retest Jev's weak spots   (issue #31)
# =====================================================================
# WHAT IS THIS FOR?
#   The first test showed Jev was weaker on neutral sentiment, rare
#   themes, German themes and Japanese sentiment, but with very few
#   examples. The first 150 reviews helped us design the fixes, so testing
#   on them again would flatter Jev. This script picks new reviews, about
#   100 in total, weighted towards those weak spots:
#     - mixed:          10 reviews with 3-4 stars per language (50)
#     - german_bad:     20 German reviews with 1-2 stars
#     - japanese_other: 10 Japanese reviews with 3-5 stars
#     - rare_theme:     up to 20 reviews with 1-2 stars that Jev thinks
#                       are about onboarding or too_easy_to_bypass
#
# WHY JEV HELPS PICK THE LAST GROUP:
#   These themes are too rare to find by chance, so Jev scans some extra
#   reviews to find likely ones. This means that group can only show how
#   often Jev is RIGHT when it picks those themes, not how many it misses.
#
# DON'T OPEN issue31_retest_scan.csv OR issue31_retest_groups.csv BEFORE
# LABELLING. They'd show you what Jev thinks and which reviews it picked.
# The sheet you label is shuffled and leaves that information out.
#
# HOW TO RUN IT (from the project folder, in a terminal where you've set
# the key with `read -s` + `export TYPESAFE_API_KEY`):
#   .venv/bin/python data/labels/make_issue31_retest_set.py
#
# IT CAN BE STOPPED AND RESTARTED: scan answers are saved as it goes.
# SAFE: it never overwrites a retest set unless you add --force.
#
# COST: 300 requests, one question each, at about 700 tokens per request.
# =====================================================================

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from typesafe_sdk import TypeSafeClient, TypeSafeError

# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LABELS_DIR = PROJECT_ROOT / "data" / "labels"

# Let this script import from the project's own folders.
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(LABELS_DIR))
from etl.complaint_themes import JEV_MODEL, QUESTION  # noqa: E402
from etl.review_filters import filter_reviews  # noqa: E402
# The same languages, stores and language check as the first test.
from make_issue31_test_set import (  # noqa: E402
    LANGUAGES, MIN_CHARS, REVIEWS_CSV, detect_language,
)

FIRST_TEST_CSV = LABELS_DIR / "issue31_test_set.csv"   # reviews to leave out
OUT_CSV = LABELS_DIR / "issue31_retest_set.csv"
GROUPS_CSV = LABELS_DIR / "issue31_retest_groups.csv"  # which group each review is in
SCAN_CSV = LABELS_DIR / "issue31_retest_scan.csv"      # Jev's scan answers (also the cache)

N_MIXED_PER_STAR = 5       # 3-star and 4-star reviews per language
N_GERMAN_BAD = 20
N_JAPANESE_OTHER = 10
N_PER_RARE_THEME = 10      # for each theme in RARE_THEMES
RARE_THEMES = ["onboarding", "too_easy_to_bypass"]
N_SCAN_PER_LANGUAGE = 60   # bad reviews per language for Jev to scan

# Not the first test's seed, so the shuffle is a new one.
RANDOM_SEED = 31

# Save scan answers to disk after this many requests.
SAVE_EVERY = 10


def load_candidates() -> pd.DataFrame:
    """Load every review we could pick, with its detected language."""
    if not REVIEWS_CSV.exists():
        sys.exit(f"Can't find {REVIEWS_CSV}. Run scrapers/ios_reviews.py first.")

    reviews = filter_reviews(pd.read_csv(REVIEWS_CSV, low_memory=False))

    stores = [country for countries in LANGUAGES.values() for country in countries]
    reviews = reviews[reviews["country"].isin(stores)].copy()

    # Ids as text everywhere, or saved scan answers wouldn't match on a re-run.
    reviews["review_id"] = reviews["review_id"].astype(str)

    reviews["body"] = reviews["body"].fillna("").str.strip()
    reviews = reviews[reviews["body"].str.len() >= MIN_CHARS]
    reviews = reviews.drop_duplicates(subset="review_id").drop_duplicates(subset="body")

    # Leave out the first test's reviews, by id and by text.
    first = pd.read_csv(FIRST_TEST_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    reviews = reviews[~reviews["review_id"].isin(first["review_id"])]
    reviews = reviews[~reviews["body"].isin(first["body"])].copy()

    print(f"New reviews to choose from: {len(reviews):,}")
    print("Detecting languages (this can take a few minutes)...")
    reviews["detected_lang"] = reviews["body"].apply(detect_language)

    # Only keep reviews in their store's language.
    keep = pd.Series(False, index=reviews.index)
    for lang, countries in LANGUAGES.items():
        keep |= reviews["country"].isin(countries) & (reviews["detected_lang"] == lang)
    return reviews[keep]


def pick_fair_groups(reviews: pd.DataFrame) -> pd.DataFrame:
    """Pick the groups chosen purely at random. Returns the picks with a `group` column."""
    picked = []

    def take(pool: pd.DataFrame, n: int, group: str):
        # Leave out anything already picked for another group.
        used = pd.concat(picked)["review_id"] if picked else []
        pool = pool[~pool["review_id"].isin(used)]
        if len(pool) < n:
            sys.exit(f"Not enough reviews for {group}: {len(pool)} found, {n} needed.")
        picked.append(pool.sample(n=n, random_state=RANDOM_SEED).assign(group=group))

    for lang in LANGUAGES:
        in_lang = reviews[reviews["detected_lang"] == lang]
        take(in_lang[in_lang["rating"] == 3], N_MIXED_PER_STAR, "mixed")
        take(in_lang[in_lang["rating"] == 4], N_MIXED_PER_STAR, "mixed")

    german = reviews[reviews["detected_lang"] == "de"]
    take(german[german["rating"] <= 2], N_GERMAN_BAD, "german_bad")

    japanese = reviews[reviews["detected_lang"] == "ja"]
    take(japanese[japanese["rating"] >= 3], N_JAPANESE_OTHER, "japanese_other")

    return pd.concat(picked, ignore_index=True)


def scan_with_jev(pool: pd.DataFrame) -> pd.DataFrame:
    """Ask Jev for the theme of each review it hasn't answered yet. Returns all answers."""
    if SCAN_CSV.exists():
        done = pd.read_csv(SCAN_CSV, dtype={"review_id": str})
    else:
        done = pd.DataFrame(columns=["review_id", "jev_theme", "jev_confidence"])

    todo = pool[~pool["review_id"].isin(done["review_id"])]
    print(f"Scan: {len(done)} already answered, {len(todo)} to ask Jev about.")
    if todo.empty:
        return done

    new_rows = []

    def save():
        new = pd.DataFrame(new_rows, columns=done.columns)
        all_rows = pd.concat([done, new], ignore_index=True) if len(done) else new
        all_rows.to_csv(SCAN_CSV, index=False)
        return all_rows

    with TypeSafeClient(model=JEV_MODEL) as client:
        for i, row in enumerate(todo.itertuples(index=False), start=1):
            try:
                response = client.system_one(
                    state={"review": row.body},
                    questions={"theme": QUESTION},
                )
            except TypeSafeError as e:
                # Save what we have, so a re-run carries on from here.
                save()
                sys.exit(f"Jev returned an error on review {row.review_id}: {e}\n"
                         f"Progress is saved. Fix the problem and run the script again.")

            answer = response.choices["theme"]
            new_rows.append({
                "review_id": row.review_id,
                "jev_theme": answer.choice,
                "jev_confidence": round(answer.confidence, 3),
            })
            # Only the count is printed, so you don't see Jev's answers before labelling.
            print(f"  {i:>3}/{len(todo)}")

            if i % SAVE_EVERY == 0:
                save()

    return save()


def pick_rare_group(reviews: pd.DataFrame, fair: pd.DataFrame) -> pd.DataFrame:
    """Scan extra bad reviews with Jev and pick the ones it gives a rare theme."""
    pool = reviews[(reviews["rating"] <= 2) & ~reviews["review_id"].isin(fair["review_id"])]
    # The same number per language, so one language can't fill the group.
    scan_pool = pd.concat([
        pool[pool["detected_lang"] == lang].sample(n=N_SCAN_PER_LANGUAGE, random_state=RANDOM_SEED)
        for lang in LANGUAGES
    ])

    answers = scan_with_jev(scan_pool)
    scanned = scan_pool.merge(answers, on="review_id")

    picked = []
    for theme in RARE_THEMES:
        found = scanned[scanned["jev_theme"] == theme]
        n = min(N_PER_RARE_THEME, len(found))
        print(f"Picked {n} of {len(found)} reviews for one rare theme.")
        picked.append(found.sample(n=n, random_state=RANDOM_SEED))

    rare = pd.concat(picked, ignore_index=True).drop(columns=["jev_theme", "jev_confidence"])
    return rare.assign(group="rare_theme")


def main():
    parser = argparse.ArgumentParser(description="Pick new reviews to retest Jev's weak spots.")
    parser.add_argument("--force", action="store_true", help="overwrite an existing retest set")
    args = parser.parse_args()

    # Don't destroy hand labels by accident.
    if OUT_CSV.exists() and not args.force:
        sys.exit(f"{OUT_CSV} already exists. Not overwriting it. "
                 f"Use --force if you really want a new one.")

    # Check before the slow language detection, not after.
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY isn't set in this terminal. Run the `read -s` and `export` steps first.")

    reviews = load_candidates()
    fair = pick_fair_groups(reviews)
    rare = pick_rare_group(reviews, fair)

    # Shuffle, so the order doesn't give away which group a review is in.
    sample = pd.concat([fair, rare], ignore_index=True)
    sample = sample.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)

    # The groups go in their own file, so the labelling sheet doesn't show them.
    sample[["review_id", "group"]].to_csv(GROUPS_CSV, index=False)

    sample = sample[["review_id", "app_key", "country", "detected_lang", "rating", "body"]].copy()
    sample["body_en"] = ""       # English translation, to help you read it
    sample["lang_ok"] = ""       # "no" if detected_lang is wrong
    sample["my_theme"] = ""      # 1-2 star reviews only: one theme from etl/complaint_themes.py
    sample["my_sentiment"] = ""  # every review: positive, neutral or negative
    sample["notes"] = ""         # anything you weren't sure about

    # utf-8-sig tells Excel the file is UTF-8, so it shows ü and 日本語 properly.
    sample.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print()
    print(f"Saved {len(sample)} reviews from {sample['app_key'].nunique()} apps to {OUT_CSV}")
    print("Don't open issue31_retest_scan.csv or issue31_retest_groups.csv before labelling.")


if __name__ == "__main__":
    main()
