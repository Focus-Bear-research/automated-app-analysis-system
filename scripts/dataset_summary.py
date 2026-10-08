# scripts/dataset_summary.py
"""
DATASET SUMMARY (GitHub issue #11)
==================================

What this script does
---------------------
It answers one question for the next team, without them opening a CSV:
    "How many apps and reviews do we have, from where, and from when?"

It reads the pipeline's curated CSV files, counts things, draws charts, and
writes the answer to:
    data/curated/DATASET_SUMMARY.md       <- the report (GitHub shows it nicely)
    data/curated/summary_charts/*.png     <- the charts the report links to
    data/curated/review_settings.json     <- remembers the review cap/countries (only
                                             written when those settings are passed in)

It is READ-ONLY on every input CSV: it never changes the data, only reports on it.

How to run it
-------------
On its own (from the repo root, with the venv active):
    python scripts/dataset_summary.py

Or automatically: scripts/refresh_all.py runs it as its last step and passes in
the review settings it used (cap, stores, countries, languages, days).

How to read this file (top to bottom)
-------------------------------------
    1. Settings & constants   - file paths, platform names, chart colours
    2. Small helpers          - turn store codes into platform names, load CSVs
    3. Review settings        - save / reload the review cap, countries, languages
    4. build_stats()          - ALL the counting happens here
    5. Markdown helpers       - number formatting and table building
    6. make_charts()          - draws the PNG charts (one block per chart)
    7. build_markdown()       - assembles the final DATASET_SUMMARY.md text
    8. main()                 - the entry point: runs steps 2 -> 7 in order

Start with main() at the bottom if you want the big picture first.
"""

# `from __future__ import annotations` lets us write type hints like `dict | None`
# on older Python versions too. It does not change how the code runs.
from __future__ import annotations

import argparse                       # reads command-line options like --review-cap 2000
import json                           # reads/writes review_settings.json
import os                             # used to build relative links between folders
import subprocess                     # runs `git` to find the current commit id
from datetime import datetime, timezone
from pathlib import Path              # Path objects make file paths easy and OS-safe

import pandas as pd                   # the table library used for all the counting


# =============================================================================
# 1. SETTINGS & CONSTANTS
#    Names in CAPITAL letters are constants: values set once and never changed.
# =============================================================================

# __file__ is this script's own path. .parents[1] goes up two levels:
# scripts/dataset_summary.py -> scripts/ -> repo root. So the script works no
# matter which folder you run it from.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURATED_DIR  = PROJECT_ROOT / "data" / "curated"   # the "/" joins path pieces

# --- Inputs (we only ever READ these) ---
APPS_ALL_CSV     = CURATED_DIR / "apps_all.csv"      # every app after normalising
APPS_CLEAN_CSV   = CURATED_DIR / "apps_clean.csv"    # apps that passed the quality filter
APPS_DROPPED_CSV = CURATED_DIR / "apps_dropped.csv"  # apps the filter removed (+ drop_reason)
REVIEWS_CSV      = CURATED_DIR / "reviews.csv"       # one row per user review
WEBSITES_CSV     = CURATED_DIR / "websites.csv"      # text scraped from each app's website

# Older datasets that also live in the repo. They are NOT used in any number in
# the report; we only list their row counts so the next team knows they exist.
OTHER_SOURCES = [
    PROJECT_ROOT / "data" / "curated" / "apps_all_clean.csv",
    PROJECT_ROOT / "data" / "reviews" / "reviews.jsonl",
]

# --- Outputs (the only files this script writes) ---
SUMMARY_MD     = CURATED_DIR / "DATASET_SUMMARY.md"
CHARTS_DIR     = CURATED_DIR / "summary_charts"
SETTINGS_JSON  = CURATED_DIR / "review_settings.json"

# If apps_clean.csv has fewer apps than this, it is probably a small test run,
# so the report shows a warning.
SMALL_DATASET_WARNING = 20

# --- Platforms ---
# The pipeline writes store names in different spellings in different files
# (e.g. "PlayStore", "playstore", "play"). This dictionary maps every spelling
# we have seen to one friendly platform name, so all counts line up.
PLATFORMS = ["Google Play", "App Store", "Chrome Web Store"]   # fixed display order
STORE_TO_PLATFORM = {
    "playstore": "Google Play", "play": "Google Play", "google_play": "Google Play",
    "appstore": "App Store", "ios": "App Store", "apple_app_store": "App Store",
    "chromews": "Chrome Web Store", "cws": "Chrome Web Store", "chrome_web_store": "Chrome Web Store",
}

# --- Chart colours ---
# Each platform ALWAYS gets the same colour in every chart, so readers learn it
# once. These three colours were checked to stay distinguishable for people
# with colour-blindness.
PLATFORM_COLORS = {"Google Play": "#2a78d6", "App Store": "#eb6834", "Chrome Web Store": "#1baf7a"}
SURFACE    = "#fcfcfb"   # chart background (off-white)
INK        = "#0b0b0b"   # main text colour
INK_2      = "#52514e"   # secondary text (axis labels, value labels)
GRID       = "#e4e3df"   # faint grid lines, so they don't compete with the data
MUTED_BAR  = "#c9c8c3"   # grey, for "dropped" apps and drop reasons
# Light-to-dark blues for heatmaps: darker = bigger number
SEQ_RAMP   = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
# Star ratings: red for bad (1-2), grey for neutral (3), blue for good (4-5)
STAR_COLORS = {1: "#b8312f", 2: "#ec8f8e", 3: "#e4e3df", 4: "#86b6ef", 5: "#2a78d6"}


# =============================================================================
# 2. SMALL HELPERS
# =============================================================================

def rel(path: Path) -> str:
    """
    Return a path relative to the repo root, for nicer printing.
    e.g. /Users/.../repo/data/curated/x.csv -> data/curated/x.csv
    If the path is outside the repo (e.g. a temp folder), print it in full.
    """
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:  # relative_to() raises ValueError when path is outside the repo
        return str(path)


def to_platform(store) -> str:
    """
    Turn a raw store value from the CSVs into a friendly platform name.
    e.g. "PlayStore" -> "Google Play", "cws" -> "Chrome Web Store".
    Lower-casing first means "AppStore" and "appstore" both match.
    """
    key = str(store).strip().lower().replace(" ", "_")
    return STORE_TO_PLATFORM.get(key, "Unknown")   # .get(..., "Unknown") = fallback if not found


def load_csv(path: Path) -> pd.DataFrame:
    """
    Read one CSV into a pandas DataFrame (a table).
    - If the file is missing, return an EMPTY table instead of crashing, so the
      rest of the report can still be written.
    - Adds a "platform" column using to_platform(), so every table can be
      grouped by the same platform names.
    """
    if not path.exists():
        print(f"[summary] missing: {rel(path)}")
        return pd.DataFrame()
    # low_memory=False stops pandas guessing column types chunk-by-chunk,
    # which avoids "mixed types" warnings on big files.
    df = pd.read_csv(path, low_memory=False)
    if "store" in df:
        # .map(function) runs the function on every value in the column
        df["platform"] = df["store"].map(to_platform)
    return df


def count_rows(path: Path) -> pd.Series:
    """
    Count rows per platform in one of the OTHER_SOURCES files.
    .jsonl = one JSON object per line, so it needs read_json(lines=True).
    usecols=["store"] reads only the column we need (faster on big files).
    """
    if path.suffix == ".jsonl":
        df = pd.read_json(path, lines=True)
    else:
        df = pd.read_csv(path, low_memory=False, usecols=["store"])
    return df["store"].map(to_platform).value_counts()   # value_counts = how many of each


# =============================================================================
# 3. REVIEW SETTINGS (review cap, stores, countries, languages, days)
#    The pipeline never saved these before, so nobody knew what cap was used.
#    Now refresh_all.py passes them in and we store them in review_settings.json.
# =============================================================================

def max_reviews_per_app(settings: dict | None) -> int | None:
    """
    The most reviews ONE app can possibly have.
    The reviews scraper applies the cap separately for every country AND every
    language, so: cap x number of countries x number of languages.
    e.g. cap 2000, countries "au,us,gb", langs "en" -> 2000 x 3 x 1 = 6000.
    Returns None if we don't know the cap.
    """
    if not settings or not settings.get("review_cap_per_app_country_lang"):
        return None
    # "au,us,gb".split(",") -> ["au", "us", "gb"]; the `if c.strip()` skips blanks
    n_countries = len([c for c in (settings.get("countries") or "x").split(",") if c.strip()])
    n_langs = len([l for l in (settings.get("langs") or "x").split(",") if l.strip()])
    return settings["review_cap_per_app_country_lang"] * n_countries * n_langs


def resolve_settings(args, settings_json: Path) -> dict | None:
    """
    Decide which review settings to show in the report.

    Case 1 - settings were passed on the command line (refresh_all.py does this
             when its reviews step ran): save them to review_settings.json and use them.
    Case 2 - nothing passed (e.g. you ran this script on its own): reuse the
             last saved review_settings.json, so the info isn't lost.
    Case 3 - nothing passed and nothing saved: return None; the report then says
             "not recorded yet".
    """
    passed = {
        "review_cap_per_app_country_lang": args.review_cap,
        "stores": args.stores,
        "countries": args.countries,
        "langs": args.langs,
        "since_days": args.since_days,
    }
    # any(...) is True if at least one setting is not None, i.e. something was passed
    if any(v is not None for v in passed.values()):                       # Case 1
        passed["recorded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        settings_json.write_text(json.dumps(passed, indent=2) + "\n")
        return passed
    if settings_json.exists():                                            # Case 2
        return json.loads(settings_json.read_text())
    return None                                                           # Case 3


# =============================================================================
# 4. BUILD_STATS - all the counting happens here
#    Input:  the five tables loaded from CSV
#    Output: one dictionary `s` holding every number/table the report needs
# =============================================================================

def build_stats(apps_all, apps_clean, apps_dropped, reviews, websites) -> dict:
    s: dict = {}

    def per_platform(df) -> pd.Series:
        """
        Count rows per platform, always returning all 3 platforms in the same
        order. .reindex(PLATFORMS, fill_value=0) adds a 0 for any platform that
        has no rows, so tables and charts never have a missing platform.
        """
        if df.empty:
            return pd.Series(0, index=PLATFORMS)
        return df["platform"].value_counts().reindex(PLATFORMS, fill_value=0)

    # --- Apps and reviews per platform ---
    s["apps_all"]     = per_platform(apps_all)
    s["apps_clean"]   = per_platform(apps_clean)
    s["apps_dropped"] = per_platform(apps_dropped)
    s["reviews"]      = per_platform(reviews)

    # --- Reviews per app ---
    # Start from the list of clean apps (app_key = unique app id, e.g. "play:cc.forestapp").
    if not apps_clean.empty:
        clean_keys = apps_clean[["app_key", "platform"]]
    else:
        clean_keys = pd.DataFrame(columns=["app_key", "platform"])
    # groupby("app_key").size() = number of review rows for each app_key
    counts = reviews.groupby("app_key").size() if not reviews.empty else pd.Series(dtype=int)
    # Look each clean app up in `counts`. Apps with no reviews get NaN (missing),
    # which fillna(0) turns into 0 - so apps with no reviews are counted as 0
    # instead of silently disappearing from the min/median.
    per_app = clean_keys.assign(n_reviews=clean_keys["app_key"].map(counts).fillna(0).astype(int))

    # The review cap applies per app PER COUNTRY AND LANGUAGE. To tell whether an
    # app "hit the cap", we need its biggest single country/language group:
    #   1. groupby(app, country, lang).size() -> reviews in each group
    #   2. .groupby("app_key").max()          -> the biggest group for each app
    group_cols = [c for c in ("app_key", "country", "lang") if c in reviews]
    if not reviews.empty:
        biggest = reviews.groupby(group_cols).size().groupby("app_key").max()
    else:
        biggest = pd.Series(dtype=int)
    per_app["max_per_country_lang"] = per_app["app_key"].map(biggest).fillna(0).astype(int)
    s["per_app"] = per_app

    # --- Review dates ---
    # The "at" column is text like "2025-10-23T04:13:03Z". to_datetime turns it
    # into real dates so we can find the oldest/newest and group by month.
    # errors="coerce" turns any unreadable date into NaT (missing) instead of crashing.
    if not reviews.empty:
        reviews = reviews.assign(date=pd.to_datetime(reviews["at"], utc=True, errors="coerce"))
    s["reviews_dated"] = reviews

    # --- Data completeness: which clean apps have each kind of data? ---
    # Website text lives in websites.csv. Find the app_keys whose text is not empty.
    text_keys = set()
    if not websites.empty and "website_text" in websites:
        has_text = websites["website_text"].fillna("").astype(str).str.strip().str.len() > 0
        text_keys = set(websites.loc[has_text, "app_key"])   # .loc[mask, col] = rows where mask is True
    s["websites_rows"] = len(websites)

    if not apps_clean.empty:
        # to_numeric(errors="coerce") turns text like "N/A" into NaN, so "> 0" works safely
        installs = pd.to_numeric(apps_clean["installs_or_users"], errors="coerce")
        rating_n = pd.to_numeric(apps_clean["rating_count"], errors="coerce")
        # One row per clean app, one True/False column per field.
        # The mean of a True/False column is the share that are True, which is
        # how the completeness heatmap gets its percentages.
        flags = pd.DataFrame({
            "platform":      apps_clean["platform"],
            "Website URL":   apps_clean["website_url"].fillna("").astype(str).str.strip() != "",
            "Website text":  apps_clean["app_key"].isin(text_keys),
            "Install count": installs.fillna(0) > 0,
            "Rating count":  rating_n.fillna(0) > 0,
            "1+ review":     per_app["n_reviews"].values > 0,
        })
    else:
        flags = pd.DataFrame(columns=["platform", "Website URL", "Website text", "Install count", "Rating count", "1+ review"])
    s["flags"] = flags

    # --- Why apps were dropped ---
    # drop_reason can hold several reasons joined by commas, e.g.
    # "below_popularity_thresholds,low_relevance". split(",") makes a list and
    # explode() gives each reason its own row, so each reason is counted.
    if not apps_dropped.empty and "drop_reason" in apps_dropped:
        s["drop_reasons"] = apps_dropped["drop_reason"].fillna("unknown").str.split(",").explode().value_counts()
    else:
        s["drop_reasons"] = pd.Series(dtype=int)
    return s


# =============================================================================
# 5. MARKDOWN HELPERS - small functions that format text for the report
# =============================================================================

def fmt(n) -> str:
    """Format a number for humans: 104512 -> "104,512", 37.5 -> "37.5", missing -> "-"."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "-"
    if isinstance(n, float) and not n.is_integer():
        return f"{n:,.1f}"
    return f"{int(n):,}"


def plural(n, word: str) -> str:
    """plural(1, "app") -> "1 app"; plural(5, "app") -> "5 apps"."""
    return f"{fmt(n)} {word}{'' if n == 1 else 's'}"


def md_table(headers: list[str], rows: list[list]) -> str:
    """
    Build a Markdown table as text. Example output:
        | Platform | Apps |
        |---|---:|
        | Google Play | 283 |
    "---:" right-aligns a column. We right-align a column only if every cell in
    it is a number (or "-"), so numbers line up and text stays left-aligned.
    """
    def numeric(col: int) -> bool:
        cells = [str(r[col]).strip("*` ").replace(",", "").replace(".", "") for r in rows]
        return all(c.isdigit() or c == "-" for c in cells)
    align = ["---:" if i > 0 and numeric(i) else "---" for i in range(len(headers))]
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(align) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def date_span(dates: pd.Series) -> tuple[str, str]:
    """Oldest and newest date as "YYYY-MM-DD" text, or ("-", "-") if there are none."""
    dates = dates.dropna()
    if dates.empty:
        return "-", "-"
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def git_commit() -> str:
    """
    The short id of the current git commit (e.g. "f630eed"), shown at the top of
    the report so readers know exactly which version of the code/data produced it.
    """
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:   # e.g. git not installed, or not inside a git repo
        return "unknown"


# =============================================================================
# 6. MAKE_CHARTS - draws the PNG charts with matplotlib
#    Every chart follows the same pattern:
#        1. check there is data (skip the chart if not)
#        2. fig, ax = plt.subplots(...)  -> create a blank figure ("fig") and plot area ("ax")
#        3. draw bars/lines/dots on `ax`, add labels and a title
#        4. save(fig, "name")            -> write the PNG and remember its path
#    Returns {chart name: png path} so build_markdown() knows which charts exist.
# =============================================================================

def make_charts(s: dict, settings: dict | None, charts_dir: Path) -> dict[str, Path]:
    # matplotlib is imported here (not at the top) so the script still works
    # without it: main() catches the ImportError and writes tables only.
    import matplotlib
    matplotlib.use("Agg")   # "Agg" = draw straight to image files, no pop-up window
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    charts_dir.mkdir(parents=True, exist_ok=True)   # create the folder if needed

    # One shared style for every chart: off-white background, grey axis text,
    # no top/right border lines, bold left-aligned titles.
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.size": 10, "text.color": INK, "axes.labelcolor": INK_2,
        "xtick.color": INK_2, "ytick.color": INK_2, "axes.edgecolor": GRID,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    })
    # A colour scale from light blue (small) to dark blue (big), for the heatmaps
    seq_cmap = LinearSegmentedColormap.from_list("seq_blue", SEQ_RAMP)
    out: dict[str, Path] = {}

    def save(fig, name: str):
        """Save one figure as <charts_dir>/<name>.png and close it to free memory."""
        path = charts_dir / f"{name}.png"
        fig.tight_layout()   # shrink margins so labels aren't cut off
        # metadata={"Software": None} stops matplotlib stamping its version into
        # the PNG, so the file only changes in git when the chart really changes.
        fig.savefig(path, dpi=150, metadata={"Software": None})
        plt.close(fig)
        out[name] = path

    def recessive_grid(ax, axis: str):
        """Faint grid lines on one axis ("x" or "y"), drawn behind the data."""
        ax.grid(axis=axis, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)

    # ---- Chart 1: apps kept vs dropped, per platform (stacked horizontal bars) ----
    kept, dropped = s["apps_clean"], s["apps_dropped"]
    if (kept.sum() + dropped.sum()) > 0:
        fig, ax = plt.subplots(figsize=(8, 2.8))          # size in inches (width, height)
        y = range(len(PLATFORMS))                         # one row per platform: 0, 1, 2
        ax.barh(y, kept.values, color=PLATFORM_COLORS["Google Play"], height=0.55, label="Kept (apps_clean)")
        # left=kept.values starts the grey "dropped" bar where the blue bar ends (= stacking)
        ax.barh(y, dropped.values, left=kept.values, color=MUTED_BAR, height=0.55,
                edgecolor=SURFACE, linewidth=2, label="Dropped (apps_dropped)")
        # Write "283 kept / 15 dropped" just after the end of each bar
        for i, (k, d) in enumerate(zip(kept.values, dropped.values)):
            ax.text(k + d, i, f"  {k:,} kept / {d:,} dropped", va="center", color=INK_2, fontsize=9)
        ax.set_yticks(list(y), PLATFORMS)
        ax.invert_yaxis()                                 # first platform at the top
        ax.set_xlim(0, max(1, (kept + dropped).max()) * 1.45)   # extra room for the labels
        ax.set_xlabel("Apps")
        ax.set_title("Apps kept vs dropped by the quality filter")
        ax.legend(frameon=False, loc="lower right", fontsize=9)
        recessive_grid(ax, "x")
        save(fig, "01_apps_kept_vs_dropped")

    # ---- Chart 2: number of reviews per platform (horizontal bars) ----
    rev = s["reviews"]
    if rev.sum() > 0:
        fig, ax = plt.subplots(figsize=(8, 2.6))
        ax.barh(PLATFORMS, rev.values, color=[PLATFORM_COLORS[p] for p in PLATFORMS], height=0.55)
        total = rev.sum()
        # Label each bar with its count and share of all reviews, e.g. "102,707 (98%)"
        for i, v in enumerate(rev.values):
            ax.text(v, i, f"  {v:,} ({v / total:.0%})", va="center", color=INK_2, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlim(0, rev.max() * 1.3)
        ax.set_xlabel("Reviews")
        ax.set_title("Reviews collected per platform")
        recessive_grid(ax, "x")
        save(fig, "02_reviews_per_platform")

    # ---- Chart 3: how many reviews each app has (box plot + one dot per app) ----
    # The box shows the middle 50% of apps, the thick line is the median. Every
    # app is also drawn as a dot so you can see clusters (e.g. many apps at 0).
    per_app = s["per_app"]
    present = [p for p in PLATFORMS if (per_app["platform"] == p).any()]   # platforms that have apps
    if present:
        import numpy as np
        # Dots are shifted up/down by a small random amount ("jitter") so they
        # don't sit on top of each other. A fixed seed (0) makes the jitter the
        # same every run, so the PNG doesn't change in git for no reason.
        rng = np.random.default_rng(0)
        fig, ax = plt.subplots(figsize=(8, 1.1 + 0.9 * len(present)))
        data = [per_app.loc[per_app["platform"] == p, "n_reviews"].values for p in present]
        # matplotlib 3.10 renamed the option for horizontal box plots; support both
        mpl_version = tuple(int(x) for x in matplotlib.__version__.split(".")[:2])
        horizontal = {"orientation": "horizontal"} if mpl_version >= (3, 10) else {"vert": False}
        ax.boxplot(data, positions=range(len(present)), widths=0.5, showfliers=False, **horizontal,
                   medianprops={"color": INK, "linewidth": 2},
                   boxprops={"color": INK_2}, whiskerprops={"color": INK_2}, capprops={"color": INK_2})
        for i, (p, vals) in enumerate(zip(present, data)):
            ax.scatter(vals, i + rng.uniform(-0.18, 0.18, len(vals)), s=22, color=PLATFORM_COLORS[p],
                       alpha=0.6, edgecolors=SURFACE, linewidths=0.8, zorder=3)
        # Dashed line = the most reviews one app could get (cap x countries x languages).
        # Only drawn if it's on a similar scale to the data, otherwise it squashes the chart.
        ceiling = max_reviews_per_app(settings)
        if ceiling and ceiling <= 1.5 * max(1, per_app["n_reviews"].max()):
            ax.axvline(ceiling, color=INK_2, linestyle="--", linewidth=1)
            ax.text(ceiling, len(present) - 0.45, f" max possible per app ({ceiling:,})", color=INK_2, fontsize=8, va="bottom")
        ax.set_yticks(range(len(present)), present)
        ax.invert_yaxis()
        ax.set_xlabel("Reviews per app (apps in apps_clean.csv, 0 if none)")
        ax.set_title("How many reviews each app has")
        recessive_grid(ax, "x")
        save(fig, "03_reviews_per_app")

    # ---- Chart 4: reviews per month, one line per platform ("from when?") ----
    rd = s["reviews_dated"]
    if not rd.empty and rd["date"].notna().any():
        # Round every date down to its month: 2025-10-23 -> 2025-10-01
        month = rd["date"].dt.tz_convert(None).dt.to_period("M").dt.to_timestamp()
        # Count reviews per (month, platform), then unstack() turns platforms into
        # columns: one row per month, one column per platform.
        monthly = rd.assign(month=month).groupby(["month", "platform"]).size().unstack(fill_value=0)
        fig, ax = plt.subplots(figsize=(8, 3.4))
        for p in PLATFORMS:
            if p in monthly:
                ax.plot(monthly.index, monthly[p], color=PLATFORM_COLORS[p], linewidth=2,
                        marker="o", markersize=5, label=p)
                # Write the platform name at the end of its line (easier than a legend)
                ax.annotate(f" {p}", (monthly.index[-1], monthly[p].iloc[-1]), color=INK_2, fontsize=8, va="center")
        ax.set_ylim(bottom=0)
        ax.set_ylabel("Reviews per month")
        ax.set_title("Review volume over time")
        ax.legend(frameon=False, fontsize=9, loc="upper left")
        recessive_grid(ax, "y")
        fig.autofmt_xdate()   # tilt the date labels so they don't overlap
        save(fig, "04_reviews_over_time")

    # ---- Chart 5: data completeness heatmap (% of clean apps that have each field) ----
    flags = s["flags"]
    if not flags.empty:
        fields = [c for c in flags.columns if c != "platform"]
        # mean() of True/False = share that is True; x100 = percentage
        pct = flags.groupby("platform")[fields].mean().mul(100).reindex([p for p in PLATFORMS if p in set(flags["platform"])])
        fig, ax = plt.subplots(figsize=(8, 1.2 + 0.6 * len(pct)))
        # imshow draws the table as coloured squares: 0% = light blue, 100% = dark blue
        ax.imshow(pct.values.astype(float), cmap=seq_cmap, vmin=0, vmax=100, aspect="auto")
        # Write the % in each square; white text on dark squares, black on light ones
        for i in range(pct.shape[0]):
            for j in range(pct.shape[1]):
                v = pct.iat[i, j]
                ax.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=9,
                        color="white" if v >= 55 else INK)
        ax.set_xticks(range(len(fields)), fields)
        ax.set_yticks(range(len(pct)), pct.index)
        ax.tick_params(length=0)
        for side in ("left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.set_title("Data completeness (% of kept apps that have each field)")
        save(fig, "05_data_completeness")

    # ---- Chart 6: reviews by country x platform (heatmap) ----
    if not rd.empty and "country" in rd:
        # pivot_table: rows = platform, columns = country, cell = number of reviews
        grid = rd.pivot_table(index="platform", columns="country", values="app_key", aggfunc="size", fill_value=0)
        grid = grid.reindex([p for p in PLATFORMS if p in grid.index])
        fig, ax = plt.subplots(figsize=(1.6 + 1.1 * grid.shape[1], 1.2 + 0.6 * len(grid)))
        top = max(1, grid.values.max())
        ax.imshow(grid.values.astype(float), cmap=seq_cmap, vmin=0, vmax=top, aspect="auto")
        for i in range(grid.shape[0]):
            for j in range(grid.shape[1]):
                v = grid.iat[i, j]
                ax.text(j, i, f"{v:,}", ha="center", va="center", fontsize=9,
                        color="white" if v / top >= 0.55 else INK)
        ax.set_xticks(range(grid.shape[1]), [c.upper() for c in grid.columns])
        ax.set_yticks(range(len(grid)), grid.index)
        ax.tick_params(length=0)
        for side in ("left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.set_title("Reviews by country and platform")
        save(fig, "06_reviews_by_country")

    # ---- Chart 7: star-rating mix per platform (100% stacked bar) ----
    # Each bar is 100% wide, split into 1-5 star segments, so platforms with
    # very different review counts can still be compared fairly.
    if not rd.empty and "rating" in rd:
        stars = pd.to_numeric(rd["rating"], errors="coerce")
        mix = rd.assign(stars=stars).dropna(subset=["stars"]).groupby(["platform", "stars"]).size().unstack(fill_value=0)
        mix = mix.reindex([p for p in PLATFORMS if p in mix.index])
        if not mix.empty:
            # Divide each row by its total -> shares; x100 -> percentages
            share = mix.div(mix.sum(axis=1), axis=0) * 100
            fig, ax = plt.subplots(figsize=(8, 1.4 + 0.6 * len(share)))
            left = pd.Series(0.0, index=share.index)   # where the next segment starts
            for star in [1, 2, 3, 4, 5]:
                vals = share[star] if star in share else pd.Series(0.0, index=share.index)
                ax.barh(share.index, vals, left=left, color=STAR_COLORS[star], height=0.55,
                        edgecolor=SURFACE, linewidth=2, label=f"{star}★")
                for i, (v, l) in enumerate(zip(vals, left)):
                    if v >= 8:   # only label segments wide enough for the text to fit
                        ax.text(l + v / 2, i, f"{v:.0f}%", ha="center", va="center", fontsize=8,
                                color="white" if star in (1, 5) else INK)
                left = left + vals
            ax.invert_yaxis()
            ax.set_xlim(0, 100)
            ax.set_xlabel("% of reviews")
            ax.set_title("Star-rating mix of collected reviews")
            ax.legend(frameon=False, ncol=5, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.35))
            save(fig, "07_star_rating_mix")

    # ---- Chart 8: why apps were dropped (horizontal bars) ----
    reasons = s["drop_reasons"]
    if not reasons.empty:
        fig, ax = plt.subplots(figsize=(8, 1.2 + 0.5 * len(reasons)))
        ax.barh(reasons.index, reasons.values, color=MUTED_BAR, height=0.55)
        for i, v in enumerate(reasons.values):
            ax.text(v, i, f"  {v:,}", va="center", color=INK_2, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlim(0, reasons.max() * 1.2)
        ax.set_xlabel("Dropped apps (one app can have several reasons)")
        ax.set_title("Why apps were dropped")
        recessive_grid(ax, "x")
        save(fig, "08_drop_reasons")

    return out


# =============================================================================
# 7. BUILD_MARKDOWN - assembles the text of DATASET_SUMMARY.md
#    We collect the report line by line in the list `L`, then join it at the end.
# =============================================================================

def build_markdown(s: dict, settings: dict | None, charts: dict[str, Path], chart_note: str | None,
                   apps_all_n: int, out_md: Path) -> str:
    per_app, rd, flags = s["per_app"], s["reviews_dated"], s["flags"]
    clean_n, dropped_n, reviews_n = int(s["apps_clean"].sum()), int(s["apps_dropped"].sum()), int(s["reviews"].sum())
    first, last = date_span(rd["date"]) if not rd.empty else ("-", "-")
    # Unique reviews: if the same review_id appears twice, it's a duplicate row
    unique_n = rd["review_id"].nunique() if "review_id" in rd else reviews_n

    def img(name: str, alt: str) -> str:
        """
        Markdown for one chart image, e.g. ![Reviews per platform](summary_charts/02_...png).
        The link is relative to the .md file, so it works on GitHub and locally.
        If the chart wasn't drawn, say why instead.
        """
        if name in charts:
            link = Path(os.path.relpath(charts[name], out_md.parent)).as_posix()
            return f"![{alt}]({link})\n"
        return f"_Chart skipped: {chart_note or 'no data for this chart.'}_\n"

    L: list[str] = []
    L.append("# Dataset summary\n")
    L.append(f"_Auto-generated by `scripts/dataset_summary.py` on "
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} at commit `{git_commit()}`. "
             f"Do not edit by hand - it is rewritten on every pipeline run._\n")

    # ---- Section: At a glance (the direct answer to issue #11) ----
    L.append("## At a glance\n")
    L.append(md_table(["Question", "Answer"], [
        ["How many apps?", f"**{fmt(clean_n)}** kept in `apps_clean.csv` (of {fmt(apps_all_n)} in `apps_all.csv`; {fmt(dropped_n)} dropped)"],
        ["How many reviews?", f"**{fmt(reviews_n)}** rows in `reviews.csv` ({fmt(unique_n)} unique review IDs)"],
        ["From where?", "; ".join(f"{p}: {plural(s['apps_clean'][p], 'app')}, {plural(s['reviews'][p], 'review')}" for p in PLATFORMS)],
        ["From when?", f"{first} to {last}"],
    ]) + "\n")

    # ---- Section: Heads-up (automatic warnings for the next team) ----
    # Each check below looks for a known data problem and adds a plain-English warning.
    warnings = []
    if clean_n < SMALL_DATASET_WARNING:
        warnings.append(f"`apps_clean.csv` has only {plural(clean_n, 'app')}. This looks like a test run, not the full dataset - "
                        f"see *Other data files* below.")
    if unique_n < reviews_n:
        warnings.append(f"{fmt(reviews_n - unique_n)} review rows repeat a `review_id` already seen "
                        f"(e.g. Google Play returning the same reviews for every country). "
                        f"Unique reviews: {fmt(unique_n)}.")
    # Google Play returns the same reviews whatever country you ask for. When the
    # pipeline removes duplicates it keeps the first copy, so every Play review
    # ends up labelled with the first country. Warn so nobody reads it as
    # "all our Play reviews are Australian".
    if not rd.empty and "country" in rd:
        play_countries = rd.loc[rd["platform"] == "Google Play", "country"].dropna().unique()
        if len(play_countries) == 1 and rd["country"].nunique() > 1:
            warnings.append(f"All Google Play reviews are labelled country `{play_countries[0]}`. Google Play returns the same "
                            f"reviews for every country and duplicates are removed, so this does not mean they are all from "
                            f"`{play_countries[0]}` - Play reviews are effectively not country-specific.")
    if s["apps_clean"]["Chrome Web Store"] > 0 and s["reviews"]["Chrome Web Store"] == 0:
        warnings.append("Chrome Web Store apps have no reviews: the reviews step only scrapes `play` and `ios`.")
    # websites.csv should have roughly one row per clean app. Far fewer means the
    # websites step was not run for this dataset, so "website text" will read ~0.
    if clean_n >= SMALL_DATASET_WARNING and s["websites_rows"] < clean_n / 2:
        warnings.append(f"`websites.csv` has only {plural(s['websites_rows'], 'row')} for {fmt(clean_n)} apps, "
                        f"so the websites step was probably not run for this dataset. Website-text counts below are not meaningful.")
    for p in PLATFORMS:
        if s["apps_clean"][p] == 0:
            warnings.append(f"No {p} apps in `apps_clean.csv`.")
    if settings is None:
        warnings.append("Review settings were never recorded. Run via `scripts/refresh_all.py` to capture them.")
    if warnings:
        L.append("> **Heads-up**\n>\n" + "\n".join(f"> - {w}" for w in warnings) + "\n")

    # ---- Section: Collection settings (review cap, countries, languages) ----
    L.append("## Collection settings\n")
    if settings:
        L.append(md_table(["Setting", "Value"], [
            ["Review cap (max reviews per app, per country, per language)", fmt(settings.get("review_cap_per_app_country_lang"))],
            ["Stores scraped for reviews", settings.get("stores") or "-"],
            ["Countries", settings.get("countries") or "-"],
            ["Languages", settings.get("langs") or "-"],
            ["Only reviews from the last N days", fmt(settings.get("since_days"))],
            ["Settings recorded at", settings.get("recorded_at", "-")],
        ]) + "\n")
    else:
        L.append("_Not recorded yet (see heads-up above)._\n")
    # Whatever was recorded, also show what the data itself contains. If the cap
    # was never recorded, the largest per-country count is the best clue to it.
    if not rd.empty:
        countries = ", ".join(sorted(rd["country"].dropna().astype(str).unique())) if "country" in rd else "-"
        langs = ", ".join(sorted(rd["lang"].dropna().astype(str).unique())) if "lang" in rd else "-"
        L.append(f"Seen in the data itself: countries **{countries}**, languages **{langs}**. "
                 f"Most reviews for one app in one country/language: **{fmt(per_app['max_per_country_lang'].max())}** "
                 f"(if the cap was not recorded, it is probably the round number just above this).\n")

    # ---- Section: Apps per platform ----
    L.append("## Apps per platform\n")
    rows = [[p, fmt(s["apps_all"][p]), fmt(s["apps_clean"][p]), fmt(s["apps_dropped"][p])] for p in PLATFORMS]
    rows.append(["**Total**", f"**{fmt(apps_all_n)}**", f"**{fmt(clean_n)}**", f"**{fmt(dropped_n)}**"])
    L.append(md_table(["Platform", "apps_all.csv", "apps_clean.csv", "apps_dropped.csv"], rows) + "\n")
    L.append(img("01_apps_kept_vs_dropped", "Apps kept vs dropped per platform"))
    if not s["drop_reasons"].empty:
        L.append(img("08_drop_reasons", "Why apps were dropped"))

    # ---- Section: Reviews per platform (+ date range per platform) ----
    L.append("## Reviews per platform\n")
    rows = []
    for p in PLATFORMS:
        sub = rd[rd["platform"] == p] if not rd.empty else rd     # only this platform's reviews
        f, l = date_span(sub["date"]) if not sub.empty else ("-", "-")
        n_apps = sub["app_key"].nunique() if not sub.empty else 0  # nunique = number of different apps
        rows.append([p, fmt(s["reviews"][p]), fmt(n_apps), f, l])
    rows.append(["**Total**", f"**{fmt(reviews_n)}**", f"**{fmt(rd['app_key'].nunique() if not rd.empty else 0)}**", first, last])
    L.append(md_table(["Platform", "Reviews", "Apps with reviews", "Oldest review", "Newest review"], rows) + "\n")
    L.append(img("02_reviews_per_platform", "Reviews per platform"))
    L.append(img("04_reviews_over_time", "Monthly review volume"))
    L.append(img("06_reviews_by_country", "Reviews by country and platform"))
    L.append(img("07_star_rating_mix", "Star-rating mix per platform"))

    # ---- Section: Reviews per app (min / median / max) ----
    L.append("## Reviews per app\n")
    cap = (settings or {}).get("review_cap_per_app_country_lang")
    L.append("Counted over every app in `apps_clean.csv`; an app with no reviews counts as 0. "
             "*Apps at the cap* = apps where at least one country/language hit the review cap, "
             "so they probably have more reviews than we collected.\n")
    rows = []
    # One row per platform, plus an "All" row. The list on the right of `in`
    # pairs each label with the matching slice of the per_app table.
    for label, sub in [(p, per_app[per_app["platform"] == p]) for p in PLATFORMS] + [("**All**", per_app)]:
        n = sub["n_reviews"]
        at_cap = fmt(int((sub["max_per_country_lang"] >= cap).sum())) if cap else "-"
        rows.append([label, fmt(len(n)),
                     fmt(n.min() if len(n) else None), fmt(float(n.median()) if len(n) else None),
                     fmt(n.max() if len(n) else None), fmt(int((n == 0).sum())), at_cap])
    L.append(md_table(["Platform", "Apps", "Min", "Median", "Max", "Apps with 0 reviews", "Apps at the cap"], rows) + "\n")
    L.append(img("03_reviews_per_app", "Reviews per app"))

    # ---- Section: Website text and install counts ----
    L.append("## Website text and install counts\n")
    rows = []
    for label, sub in [(p, flags[flags["platform"] == p]) for p in PLATFORMS] + [("**All**", flags)]:
        # .sum() of a True/False column = how many are True
        rows.append([label, fmt(len(sub)), fmt(int(sub["Website text"].sum())), fmt(int(sub["Install count"].sum())),
                     fmt(int(sub["Website URL"].sum()))])
    L.append(md_table(["Platform", "Apps", "With website text", "With install count", "With website URL"], rows) + "\n")
    L.append("App Store does not publish install counts, so 0 there is expected. "
             "Website text comes from `websites.csv` (non-empty `website_text`).\n")
    L.append(img("05_data_completeness", "Data completeness heatmap"))

    # ---- Section: Other data files (only if they exist) ----
    others = [p for p in OTHER_SOURCES if p.exists()]
    if others:
        L.append("## Other data files in the repo\n")
        L.append("Older or larger datasets that the current pipeline outputs above do **not** come from. "
                 "Listed so you know what exists; not used in any number above.\n")
        rows = []
        for path in others:
            c = count_rows(path).reindex(PLATFORMS, fill_value=0)
            rows.append([f"`{rel(path)}`", fmt(c.sum())] + [fmt(c[p]) for p in PLATFORMS])
        L.append(md_table(["File", "Rows"] + PLATFORMS, rows) + "\n")

    return "\n".join(L)


# =============================================================================
# 8. MAIN - the entry point. Runs when you type `python scripts/dataset_summary.py`.
# =============================================================================

def main():
    # --- Step 1: read command-line options (all optional) ---
    ap = argparse.ArgumentParser(description="Summarise the curated dataset into DATASET_SUMMARY.md (+ charts)")
    ap.add_argument("--curated-dir", type=Path, default=CURATED_DIR,
                    help="Folder holding apps_*.csv, reviews.csv, websites.csv (e.g. a backup)")
    ap.add_argument("--out", type=Path, default=None, help="Default: <curated-dir>/DATASET_SUMMARY.md")
    ap.add_argument("--charts-dir", type=Path, default=None, help="Default: <curated-dir>/summary_charts")
    ap.add_argument("--no-charts", action="store_true", help="Write the tables only")
    # The settings the reviews step used. refresh_all.py passes these in; you can
    # also pass them by hand, e.g. --review-cap 2000 --countries au,us,gb
    ap.add_argument("--review-cap", type=int, default=None)
    ap.add_argument("--stores", default=None)
    ap.add_argument("--countries", default=None)
    ap.add_argument("--langs", default=None)
    ap.add_argument("--since-days", type=int, default=None)
    args = ap.parse_args()
    cur = args.curated_dir
    # `a or b` means "use a, unless it's empty/None, then use b"
    args.out = args.out or cur / SUMMARY_MD.name
    args.charts_dir = args.charts_dir or cur / CHARTS_DIR.name

    # --- Step 2: load the five input tables (read-only) ---
    apps_all     = load_csv(cur / APPS_ALL_CSV.name)
    apps_clean   = load_csv(cur / APPS_CLEAN_CSV.name)
    apps_dropped = load_csv(cur / APPS_DROPPED_CSV.name)
    reviews      = load_csv(cur / REVIEWS_CSV.name)
    websites     = load_csv(cur / WEBSITES_CSV.name)

    # --- Step 3: work out the review settings, then all the numbers ---
    settings = resolve_settings(args, cur / SETTINGS_JSON.name)
    stats = build_stats(apps_all, apps_clean, apps_dropped, reviews, websites)

    # --- Step 4: draw the charts (skipped if --no-charts or matplotlib is missing) ---
    charts, chart_note = {}, None
    if args.no_charts:
        chart_note = "charts turned off (--no-charts)."
    else:
        try:
            charts = make_charts(stats, settings, args.charts_dir)
        except ImportError:   # matplotlib isn't installed: still write the tables
            chart_note = "matplotlib is not installed (`pip install matplotlib`)."
            print(f"[summary] {chart_note}")

    # --- Step 5: write DATASET_SUMMARY.md ---
    md = build_markdown(stats, settings, charts, chart_note, len(apps_all), args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md)
    print(f"[summary] wrote {rel(args.out)} ({len(charts)} charts)")


# This line means: only run main() when the file is run directly
# (`python scripts/dataset_summary.py`), not when another file imports it.
if __name__ == "__main__":
    main()
