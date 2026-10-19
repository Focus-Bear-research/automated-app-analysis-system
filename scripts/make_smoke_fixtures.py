"""
scripts/make_smoke_fixtures.py  -  build the tiny test dataset   (issue #8)

WHAT IS A "FIXTURE"?
    A fixture is a small, fixed set of test data that is saved in the repo.
    The smoke run (scripts/smoke_run.sh) feeds it through every pipeline
    stage. Because the data never changes, any new error must come from a
    code change - which is exactly what we want to detect.

WHAT THIS SCRIPT DOES
    It copies a hand-picked handful of apps (and 50 of their reviews) out of
    the real data in data/input and data/curated, and saves them in
    tests/fixtures/smoke/. You only need to run it again if you want to
    change which apps are in the test set.

HOW TO RUN IT (from the project folder):
    .venv/bin/python scripts/make_smoke_fixtures.py
"""

# --- Imports: load the tools this script uses -------------------------
import json                 # read/write .jsonl files (one JSON object per line)
import re                   # "regular expressions": pattern matching in text
from pathlib import Path    # build file paths that work on Mac and Windows

import pandas as pd         # tables (DataFrames), read/write CSV


# --- Where things are --------------------------------------------------
# Path(__file__) is this script's own location. .parents[1] goes up two
# levels (scripts/ -> project folder), so paths work from any folder.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_DUMP     = PROJECT_ROOT / "data" / "input" / "full_dump.jsonl"
REAL_REVIEWS  = PROJECT_ROOT / "data" / "curated" / "reviews.csv"
REAL_LLM      = PROJECT_ROOT / "data" / "curated" / "features_llm.csv"
FIXTURE_DIR   = PROJECT_ROOT / "tests" / "fixtures" / "smoke"


# --- The test apps, and WHY each one is included -----------------------
# A good test set is small but covers every kind of case the code must
# handle: each store, each app type, and apps that SHOULD be dropped.
FIXTURE_APPS = {
    # app_key                                  : reason it is in the test set
    "play:cc.forestapp":                         "Google Play, DSCT focus app, many reviews",
    "play:co.thefabulous.app":                   "Google Play, habit tracker",
    "play:com.gmail.jmartindev.timetune":        "Google Play, planner",
    "ios:id1480220328":                          "App Store, planner marketed for ADHD (Tiimo)",
    "ios:id1478345385":                          "App Store, focus timer with few reviews",
    "cws:ifdepgnnjpnbkcgempionjablajancjc":      "Chrome Web Store, site blocker, NO reviews (edge case)",
    "play:co.bitbakery.BrainFit":                "SHOULD BE DROPPED by cleaning: weak scope",
    "ios:id6760403444":                          "SHOULD BE DROPPED by cleaning: too few ratings",
}

REVIEWS_PER_APP = 10   # 5 apps have reviews x 10 = 50 reviews in total

# Same idea as the ADHD keyword flag in llm/sentiment_pipeline.py: we make
# sure some test reviews mention ADHD, so the ADHD code path gets exercised.
ADHD_WORDS = re.compile(r"\b(?:adhd|focus|distract\w*|procrastinat\w*)\b", re.IGNORECASE)


def build_dump() -> int:
    """Copy the raw scraped records of the test apps into full_dump.jsonl."""
    kept = {}
    # Read the real file line by line. Each line is one app as JSON text.
    with REAL_DUMP.open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)              # JSON text -> Python dict
            key = record.get("app_key")
            # Keep only test apps, and only the first copy if one appears twice.
            if key in FIXTURE_APPS and key not in kept:
                kept[key] = record

    # Warn (instead of silently continuing) if an app could not be found.
    missing = set(FIXTURE_APPS) - set(kept)
    if missing:
        raise SystemExit(f"These test apps are not in {REAL_DUMP.name}: {sorted(missing)}")

    with (FIXTURE_DIR / "full_dump.jsonl").open("w", encoding="utf-8") as f:
        for key in FIXTURE_APPS:                   # same order as the list above
            f.write(json.dumps(kept[key], ensure_ascii=False) + "\n")
    return len(kept)


def pick_reviews(app_reviews: pd.DataFrame) -> pd.DataFrame:
    """Choose REVIEWS_PER_APP reviews for one app, mixing ADHD and star ratings.

    We sort by review_id first, so the choice is the same every time the
    script runs ("deterministic"), rather than random.
    """
    app_reviews = app_reviews.sort_values("review_id")
    mentions_adhd = app_reviews["body"].fillna("").str.contains(ADHD_WORDS)

    # Up to 3 reviews that mention ADHD/focus words...
    adhd_part = app_reviews[mentions_adhd].head(3)
    # ...then fill the rest with one review per star rating (1 to 5), and repeat,
    # so we get a mix of happy and unhappy reviews.
    rest = app_reviews.drop(adhd_part.index)
    rest = rest.assign(_rank=rest.groupby("rating").cumcount()).sort_values(["_rank", "rating"])
    rest_part = rest.head(REVIEWS_PER_APP - len(adhd_part)).drop(columns="_rank")

    return pd.concat([adhd_part, rest_part])


def build_reviews() -> int:
    """Save 50 reviews (10 per app) for the apps that have reviews."""
    reviews = pd.read_csv(REAL_REVIEWS)
    reviews = reviews[reviews["app_key"].isin(FIXTURE_APPS)]
    # groupby splits the table into one small table per app; we pick from each.
    chosen = pd.concat(pick_reviews(group) for _, group in reviews.groupby("app_key"))
    chosen.to_csv(FIXTURE_DIR / "reviews.csv", index=False)
    return len(chosen)


def build_websites() -> int:
    """Save a websites.csv with the columns etl/scrape_websites.py produces.

    The website TEXT is left empty on purpose: the smoke run must work
    offline, and we don't want to invent website content.
    """
    rows = []
    with (FIXTURE_DIR / "full_dump.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rows.append({
                "app_key": r["app_key"], "store": r.get("store"), "id": r.get("id"),
                "title": r.get("title"), "website_url": r.get("website_url"),
                "final_url": "", "website_status": "", "content_len": 0,
                "website_text": "", "page_title": "", "scraped_at": r.get("scraped_at"),
            })
    pd.DataFrame(rows).to_csv(FIXTURE_DIR / "websites.csv", index=False)
    return len(rows)


def build_llm_features() -> int:
    """Save the recorded LLM answers for the test apps.

    The real LLM step costs money and needs an API key, so the smoke run
    uses these saved answers to test the steps that come AFTER the LLM.
    """
    llm = pd.read_csv(REAL_LLM)
    llm = llm[llm["app_key"].isin(FIXTURE_APPS)]
    llm.to_csv(FIXTURE_DIR / "features_llm.csv", index=False)
    return len(llm)


def write_readme(counts: dict) -> None:
    """Write a short README in the fixture folder explaining what is there."""
    lines = [
        "# Smoke-test fixture data",
        "",
        "Tiny, fixed test data used by `scripts/smoke_run.sh` (issue #8).",
        "Re-create it with `.venv/bin/python scripts/make_smoke_fixtures.py`.",
        "",
        "| File | Rows | What it is |",
        "|---|---|---|",
        f"| full_dump.jsonl | {counts['dump']} | raw scraped app records (input to normalize) |",
        f"| reviews.csv | {counts['reviews']} | real reviews, 10 per app, mixed stars, some mention ADHD/focus |",
        f"| websites.csv | {counts['web']} | website columns only; text left empty so the run works offline |",
        f"| features_llm.csv | {counts['llm']} | saved LLM feature answers, so no API key is needed |",
        "",
        "## Apps and why each is included",
        "",
        "| app_key | Why |",
        "|---|---|",
    ]
    lines += [f"| `{key}` | {why} |" for key, why in FIXTURE_APPS.items()]
    (FIXTURE_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# This block only runs when you run the file directly (not when imported).
if __name__ == "__main__":
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    counts = {
        "dump": build_dump(),
        "reviews": build_reviews(),
        "web": build_websites(),
        "llm": build_llm_features(),
    }
    write_readme(counts)
    print(f"Fixture written to {FIXTURE_DIR.relative_to(PROJECT_ROOT)}/ : {counts}")
