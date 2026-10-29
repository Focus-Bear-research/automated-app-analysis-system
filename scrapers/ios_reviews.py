# scrapers/ios_reviews.py
"""
Scrape iOS App Store reviews for competitor apps.

Two methods:
  rss    - free. Apple's public customer reviews RSS feed. Apple caps this at
           the 500 most recent reviews per app per country, so we loop over
           many countries to collect more.
  apify  - paid ($0.10 per 1,000 reviews). Uses the Apify actor
           thewolves/appstore-reviews-scraper. Needs APIFY_TOKEN in .env.

Output uses the same columns as reviews_pipeline.py, so the rows can be
merged into data/curated/reviews.csv later.

Examples:
  python -m scrapers.ios_reviews --method rss --app-ids 1450486923 --countries us
  python -m scrapers.ios_reviews --method apify --app-ids 1450486923 --countries us --max-per-app 100
  python -m scrapers.ios_reviews --method rss --limit-apps 5
  python -m scrapers.ios_reviews --method rss --groups app_blocker,adhd,focus_timer,habit_routine
"""
import argparse
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import requests

from scrapers.reviews_pipeline import (
    append_rows_to_csv,
    compute_app_key,
    is_special_review,
    norm_ios_id,
)

UTC = timezone.utc

# The only Apify actor we use for App Store reviews
APIFY_ACTOR = "thewolves/appstore-reviews-scraper"
APIFY_PRICE_PER_REVIEW = 0.0001

# Apple's RSS feed returns at most 10 pages of 50 reviews
RSS_MAX_PAGES = 10

# English speaking storefronts first, then other big markets
DEFAULT_COUNTRIES = "us,gb,ca,au,nz,ie,in,sg,za,de,fr,nl,se,es,it,br,mx,jp"


# ------------------ helpers ------------------

def load_env(path: str = ".env") -> None:
    """Load KEY=VALUE lines from .env into os.environ (no extra package needed)."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def to_iso(value: Any) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def make_row(app_id: str, country: str, lang: str, review_id: str, user_name: str,
             rating: Any, title: str, body: str, version: str, at: str | None) -> Dict[str, Any]:
    return {
        "app_key": compute_app_key("AppStore", app_id),
        "store": "AppStore",
        "app_id": app_id,
        "country": country,
        "lang": lang,
        "review_id": review_id,
        "user_name": user_name,
        "rating": rating,
        "title": title,
        "body": body,
        "version": version,
        "at": at,
        "special_reviews": is_special_review(title, body),
    }


def load_app_ids(inp: str, app_ids_arg: str | None, limit_apps: int | None,
                 groups: str | None = None) -> List[str]:
    """App IDs from --app-ids, or every ios:idXXXX app_key in the input CSV.
    If the CSV has a 'group' column, --groups keeps only those groups."""
    if app_ids_arg:
        ids = [norm_ios_id(x) for x in app_ids_arg.split(",") if x.strip()]
    else:
        df = pd.read_csv(inp, dtype=str).fillna("")
        if groups and "group" in df.columns:
            df = df[df["group"].isin([g.strip() for g in groups.split(",")])]
        keys = df["app_key"][df["app_key"].str.startswith("ios:")]
        ids = [norm_ios_id(k) for k in keys.drop_duplicates()]
    return ids[:limit_apps] if limit_apps else ids


def read_seen_ids(csv_path: Path) -> set:
    """(app_id, review_id) pairs already saved, so re-runs don't add duplicates."""
    if not csv_path.exists():
        return set()
    df = pd.read_csv(csv_path, dtype=str, usecols=["app_id", "review_id"]).fillna("")
    return set(zip(df["app_id"], df["review_id"]))


# ------------------ method 1: free RSS feed ------------------

def get_rss_page(url: str, lang: str, retries: int = 4) -> Dict[str, Any] | None:
    """Apple's feed sometimes fails for a moment, so retry with a growing wait.
    Returns the JSON, or None if every attempt failed."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params={"l": lang}, timeout=20)
            if resp.status_code == 200:
                return resp.json()
            reason = f"HTTP {resp.status_code}"
        except (requests.RequestException, ValueError) as e:
            reason = str(e)
        if attempt < retries:
            time.sleep(2 * attempt)
    print(f"    [rss] gave up after {retries} tries ({reason}): {url}")
    return None


def get_rss_reviews(url: str, lang: str) -> List[Dict[str, Any]] | None:
    """Review entries on one feed page. None means the request itself failed."""
    data = get_rss_page(url, lang)
    if data is None:
        return None
    entries = data.get("feed", {}).get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    # The first entry can be the app itself, real reviews have a rating
    return [e for e in entries if "im:rating" in e]


def fetch_rss(app_id: str, country: str, lang: str, max_per_app: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    prev_page_full = True
    empty_in_a_row = 0
    for page in range(1, RSS_MAX_PAGES + 1):
        url = (f"https://itunes.apple.com/{country}/rss/customerreviews/"
               f"page={page}/id={app_id}/sortby=mostrecent/json")
        reviews = get_rss_reviews(url, lang)
        if reviews is None:
            break

        # Apple sometimes returns an empty page in the middle of the results (HTTP 200,
        # no entries). If the previous page was full, the empty page is probably one of
        # those gaps, so retry it and then move on instead of stopping.
        if not reviews and prev_page_full:
            for attempt in range(2):
                time.sleep(2 * (attempt + 1))
                reviews = get_rss_reviews(url, lang) or []
                if reviews:
                    break
        if not reviews:
            empty_in_a_row += 1
            # A short page before this means we reached the real end. Several empty
            # pages in a row means the feed has nothing more for this country.
            # An empty first page means the app has no reviews in this country.
            if page == 1 or not prev_page_full or empty_in_a_row >= 3:
                break
            continue
        empty_in_a_row = 0
        prev_page_full = len(reviews) >= 50

        for e in reviews:
            rows.append(make_row(
                app_id=app_id,
                country=country,
                lang=lang,
                review_id=e.get("id", {}).get("label", ""),
                user_name=e.get("author", {}).get("name", {}).get("label", ""),
                rating=int(e.get("im:rating", {}).get("label") or 0),
                title=e.get("title", {}).get("label", ""),
                body=e.get("content", {}).get("label", ""),
                version=e.get("im:version", {}).get("label", ""),
                at=to_iso(e.get("updated", {}).get("label")),
            ))
            if len(rows) >= max_per_app:
                return rows
        time.sleep(0.3)
    return rows


# ------------------ method 2: Apify actor ------------------

def fetch_apify(client, app_id: str, country: str, lang: str, max_per_app: int) -> List[Dict[str, Any]]:
    # Price is $0.0001 per review, so cap the spend a little above the expected cost
    max_charge = Decimal(str(round(max_per_app * APIFY_PRICE_PER_REVIEW * 1.2 + 0.01, 4)))
    run = client.actor(APIFY_ACTOR).call(
        run_input={"appIds": [app_id], "country": country, "maxItems": max_per_app},
        max_total_charge_usd=max_charge,
    )
    if not run:
        print(f"    [apify] {country}: run did not return")
        return []

    rows: List[Dict[str, Any]] = []
    empty = 0
    for item in client.dataset(run.default_dataset_id).iterate_items():
        if item.get("noResults") or item.get("error"):
            empty += 1
            continue
        rows.append(make_row(
            app_id=app_id,
            country=item.get("country") or country,
            lang=lang,
            review_id=str(item.get("id", "")),
            user_name=item.get("userName", ""),
            rating=item.get("score"),
            title=item.get("title", ""),
            body=item.get("text", ""),
            version=item.get("version", ""),
            at=to_iso(item.get("date")),
        ))
    if empty and not rows:
        print(f"    [apify] {country}: actor returned only noResults rows "
              f"(status: {run.status_message})")
    return rows


# ------------------ runner ------------------

def main():
    ap = argparse.ArgumentParser(description="Scrape iOS App Store reviews (RSS or Apify)")
    ap.add_argument("--method", choices=["rss", "apify"], default="rss")
    ap.add_argument("--in", dest="inp", default="data/curated/competitor_apps.csv",
                    help="CSV with an app_key column (ios:idXXXX)")
    ap.add_argument("--app-ids", help="comma list of App Store IDs, overrides --in")
    ap.add_argument("--limit-apps", type=int, help="only scrape the first N apps (for testing)")
    ap.add_argument("--groups", help="comma list of groups from competitor_apps.csv, e.g. app_blocker,adhd")
    ap.add_argument("--countries", default=DEFAULT_COUNTRIES, help="comma list of country codes")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--max-per-app", type=int, default=500,
                    help="max reviews per app per country")
    ap.add_argument("--out-csv", default="data/curated/ios_reviews.csv")
    args = ap.parse_args()

    app_ids = load_app_ids(args.inp, args.app_ids, args.limit_apps, args.groups)
    countries = [c.strip().lower() for c in args.countries.split(",") if c.strip()]
    out = Path(args.out_csv)
    seen = read_seen_ids(out)

    client = None
    if args.method == "apify":
        load_env()
        token = os.environ.get("APIFY_TOKEN")
        if not token:
            raise SystemExit("APIFY_TOKEN is missing. Add it to .env (never commit it).")
        from apify_client import ApifyClient
        client = ApifyClient(token)

    print(f"Method: {args.method} | apps: {len(app_ids)} | countries: {','.join(countries)} "
          f"| max per app per country: {args.max_per_app}")

    total_new = 0
    for i, app_id in enumerate(app_ids, 1):
        print(f"[{i}/{len(app_ids)}] app {app_id}")
        for country in countries:
            if args.method == "rss":
                rows = fetch_rss(app_id, country, args.lang, args.max_per_app)
            else:
                rows = fetch_apify(client, app_id, country, args.lang, args.max_per_app)

            new_rows = []
            for r in rows:
                key = (r["app_id"], r["review_id"])
                if r["review_id"] and key not in seen:
                    seen.add(key)
                    new_rows.append(r)
            append_rows_to_csv(out, new_rows)
            total_new += len(new_rows)
            print(f"    {country}: {len(rows)} fetched, {len(new_rows)} new")

    print(f"Done. {total_new} new reviews saved to {out}")


if __name__ == "__main__":
    main()
