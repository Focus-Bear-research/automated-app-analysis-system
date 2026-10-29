# etl/review_filters.py
# =====================================================================
# Shared review filters   (issue #25)
# =====================================================================
# WHAT IS THIS FOR?
#   Jeremy asked for two clean-ups before analysing competitor reviews:
#     1. leave out apps that aren't Focus Bear competitors
#        (the list is `exclude_app_keys` in scrapers/seeds.yml)
#     2. remove reviews that have no app_key, because we can't tell
#        which app they are about
#   Keeping both rules here, in one place, means every script that uses
#   them (the review scraper, the test set, the Jev analysis) filters the
#   same way.
#
# HOW TO USE IT:
#   from etl.review_filters import filter_reviews, load_excluded_app_keys
#   reviews = filter_reviews(reviews)            # prints what it removed
# =====================================================================

from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEEDS_YML = PROJECT_ROOT / "scrapers" / "seeds.yml"


def load_excluded_app_keys(seeds_path: Path = SEEDS_YML) -> set[str]:
    """Read the app_keys listed under `exclude_app_keys` in seeds.yml.

    Returns an empty set if the file or the list is missing, so nothing
    breaks on an older seeds.yml.
    """
    if not seeds_path.exists():
        return set()
    cfg = yaml.safe_load(seeds_path.read_text()) or {}
    return {str(k).strip() for k in (cfg.get("exclude_app_keys") or [])}


def filter_reviews(reviews: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Remove reviews with no app_key, and reviews of excluded apps.

    `reviews` must have an `app_key` column. Returns a new DataFrame;
    the one passed in is not changed.
    """
    if "app_key" not in reviews.columns:
        raise ValueError("filter_reviews needs an 'app_key' column")

    before = len(reviews)

    # 1. No app_key: empty cells come in as NaN or as "" depending on how
    #    the CSV was read, so treat both as missing.
    keys = reviews["app_key"].fillna("").astype(str).str.strip()
    has_key = keys != ""

    # 2. Excluded (non-competitor) apps from seeds.yml.
    excluded = load_excluded_app_keys()
    not_excluded = ~keys.isin(excluded)

    kept = reviews[has_key & not_excluded].copy()

    if verbose:
        print(f"filter_reviews: {before:,} reviews in")
        print(f"  - {(~has_key).sum():,} removed: no app_key")
        print(f"  - {(has_key & ~not_excluded).sum():,} removed: excluded app ({len(excluded)} apps in seeds.yml)")
        print(f"  = {len(kept):,} reviews kept")
    return kept
