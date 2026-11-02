# scripts/build_competitor_list.py
"""
Build the list of competitor apps worth scraping reviews for.

Starts from data/curated/apps_all_clean.csv and keeps apps that are:
  1. relevant to Focus Bear (focus, blocking, screen time, habits, routines, ADHD...)
  2. popular enough to have useful reviews
       - iOS:  Apple doesn't publish downloads, so we use the rating count
       - Play: installs and rating count

Output: data/curated/competitor_apps.csv (used by scrapers/ios_reviews.py)

Example:
  python -m scripts.build_competitor_list
  python -m scripts.build_competitor_list --min-ios-ratings 500 --min-play-installs 50000
"""
import argparse
import re

import pandas as pd

# An app is relevant if its title or description mentions one of these
RELEVANT_RX = re.compile(
    r"\bfocus\w*|distract\w*|\bblock\w*|screen ?time|\bhabit\w*|\broutine\w*|"
    r"\badhd\b|\baudhd\b|\bautis\w*|neurodiver\w*|executive function\w*|"
    r"pomodoro|procrastinat\w*|deep work|self[- ]?control|digital (?:wellbeing|detox)|"
    r"\bplanner\b|to-?do list|time block\w*",
    re.I,
)

# Big apps that match the keywords by accident but are not competitors
EXCLUDE_TITLE_RX = re.compile(
    r"\bpdf\b|microsoft|\boffice\b|\bword\b|excel|powerpoint|google drive|dropbox|"
    r"scanner|caller|call block|calls blacklist|browser|chatgpt|copilot|grok|perplexity|"
    r"\bgps\b|bible|prayer|devotional|english|\bvpn\b|app ?lock|smart home|alarm clock|"
    r"spam call|onenote|dating",
    re.I,
)

OUT_COLS = [
    "app_key", "platform", "app_id", "title", "developer", "category", "group",
    "rating_count", "rating_avg", "installs", "store_url", "matched_keywords",
]

# Rough competitor groups, checked in order against the title (first match wins)
GROUPS = [
    ("adhd", r"\badhd\b|\bautis|neurodiver|\bnd\b|executive"),
    ("parental_control", r"parental|family|kids|child|mspy|famisafe|qustodio|ourpact|kidslox|circle"),
    ("content_blocker", r"porn|adblock|ad block|ads blocker|ad remover|1blocker|adguard|adlock|wipr|nofap|no nut|covenant|truple|safe surfer"),
    ("app_blocker", r"block|screen ?time|detox|one sec|opal|freedom|offscreen|unpluq|lock me out|noscroll|digitox|yourhour|minimalist phone|launcher|touch grass|bepresent|cape|refocus|roots|ascent|app limit"),
    ("focus_timer", r"focus|pomodoro|forest|flora|study|flipd|engross|focus timer"),
    # Meditation apps with "habit" in the name (e.g. Simple Habit) belong with meditation
    ("meditation_wellbeing", r"meditat"),
    ("habit_routine", r"habit|routine|streak|atoms|me\+|fabulous|tiimo|structured|brite|daily planner"),
    ("meditation_wellbeing", r"meditat|sleep|calm|headspace|mindful|breath|yoga|journal|affirmation|relax|cbt|mental|hypno|zen|chakra"),
    ("planner_todo", r"to-?do|task|planner|schedule|notion|todoist|ticktick|any\.do|trello|asana|evernote|tracker"),
]


def assign_group(title: str) -> str:
    for name, pattern in GROUPS:
        if re.search(pattern, title or "", re.I):
            return name
    return "other"


def matched_keywords(text: str) -> str:
    found = {m.group(0).lower() for m in RELEVANT_RX.finditer(text or "")}
    return ", ".join(sorted(found))


def main():
    ap = argparse.ArgumentParser(description="Build the competitor app list for review scraping")
    ap.add_argument("--in", dest="inp", default="data/curated/apps_all_clean.csv")
    ap.add_argument("--out", default="data/curated/competitor_apps.csv")
    ap.add_argument("--min-ios-ratings", type=int, default=1000)
    ap.add_argument("--min-play-installs", type=int, default=100000)
    ap.add_argument("--min-play-ratings", type=int, default=1000)
    ap.add_argument("--exclude-categories", default="Utilities",
                    help="comma list of store categories to drop")
    ap.add_argument("--exclude-groups", default="content_blocker",
                    help="comma list of groups to drop (ad blockers, porn blockers...)")
    args = ap.parse_args()

    df = pd.read_csv(args.inp)
    df["platform"] = df["app_key"].str.split(":").str[0]
    df = df[df["platform"].isin(["ios", "play"])].copy()

    df["rating_count"] = pd.to_numeric(df["rating_count"], errors="coerce").fillna(0).astype(int)
    df["installs"] = pd.to_numeric(df["installs_or_users"], errors="coerce").fillna(0).astype(int)
    df["matched_keywords"] = (df["title"].fillna("") + " " + df["description"].fillna("")).map(matched_keywords)
    df["app_id"] = df["app_key"].str.split(":", n=1).str[1]

    excluded_cats = [c.strip().lower() for c in args.exclude_categories.split(",") if c.strip()]
    relevant = (
        (df["matched_keywords"] != "")
        & ~df["title"].fillna("").str.contains(EXCLUDE_TITLE_RX)
        & ~df["category"].fillna("").str.lower().isin(excluded_cats)
    )
    popular_ios = (df["platform"] == "ios") & (df["rating_count"] >= args.min_ios_ratings)
    popular_play = (
        (df["platform"] == "play")
        & (df["installs"] >= args.min_play_installs)
        & (df["rating_count"] >= args.min_play_ratings)
    )

    out = df[relevant & (popular_ios | popular_play)]
    out = out.drop_duplicates("app_key").sort_values(["platform", "rating_count"], ascending=[True, False])
    out["group"] = out["title"].map(assign_group)
    excluded_groups = [g.strip() for g in args.exclude_groups.split(",") if g.strip()]
    out = out[~out["group"].isin(excluded_groups)]
    out[OUT_COLS].to_csv(args.out, index=False)

    print(f"Input apps (ios + play): {len(df)}")
    print(f"Relevant: {relevant.sum()} | relevant and popular: {len(out)}")
    print(pd.crosstab(out["group"], out["platform"]).to_string())
    print(f"Saved to {args.out}")


if __name__ == "__main__":
    main()
