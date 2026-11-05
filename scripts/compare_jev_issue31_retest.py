# scripts/compare_jev_issue31_retest.py
# =====================================================================
# Retest Jev's weak spots on new hand-labelled reviews   (issue #31)
# =====================================================================
# WHAT IS THIS FOR?
#   The first test showed Jev rarely matched neutral labels, partly
#   because of how the sentiment question was worded. This script asks
#   Jev the old and new wording side by side on NEW reviews, and checks
#   the other weak spots: rare themes, German themes and Japanese
#   sentiment. It only uses the original text, since translating made
#   little difference in the first test.
#
# HOW TO RUN IT (from the project folder, in a terminal where you've set
# the key with `read -s` + `export TYPESAFE_API_KEY`):
#   .venv/bin/python scripts/compare_jev_issue31_retest.py
#
# IT CAN BE STOPPED AND RESTARTED: answers are saved as it goes, and a
# re-run only asks Jev about reviews it hasn't answered yet.
#
# COST: one request per review (about 100). The tokens used are printed
# at the end.
# =====================================================================

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from typesafe_sdk import Choice, TypeSafeClient, TypeSafeError

# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Let this script import from the project's own folders (e.g. etl/).
sys.path.insert(0, str(PROJECT_ROOT))
from etl.complaint_themes import JEV_MODEL, QUESTION  # noqa: E402
from scripts.compare_jev_issue31 import SENTIMENT_QUESTION, load_labels, score  # noqa: E402
from scripts.compare_jev_test_set import to_markdown  # noqa: E402

LABELS_DIR = PROJECT_ROOT / "data" / "labels"

LABELS_XLSX = LABELS_DIR / "issue31_retest_labelling.xlsx"              # your hand labels (input)
GROUPS_CSV = LABELS_DIR / "issue31_retest_groups.csv"                   # which group each review is in
RESULTS_CSV = LABELS_DIR / "issue31_retest_jev_results.csv"             # Jev's answers (output, also the cache)
DISAGREEMENTS_CSV = LABELS_DIR / "issue31_retest_disagreements.csv"     # every answer that differs from your label
RECHECKS_CSV = LABELS_DIR / "issue31_retest_rechecks.csv"               # labels changed after seeing Jev's answers

# Save progress to disk after this many requests.
SAVE_EVERY = 10

# Review numbers (the `no` column) whose labels weren't made independently.
NOT_INDEPENDENT = [1, 4, 17]

# The new wording: a clear rule for reviews that both praise and complain.
SENTIMENT_QUESTION_V2 = Choice(
    instructions="This is an app store review. What is the reviewer's overall sentiment about the app?",
    criteria={
        "positive": "Only praise, with no clear complaint or request.",
        "neutral": "Both clear praise and a clear complaint or request. Also a description, "
                   "question or request with no opinion either way.",
        "negative": "Mainly complaints, even if they briefly say something nice.",
    },
)

# The two wordings to compare: name in the results -> question.
SENTIMENT_VERSIONS = {"v1": SENTIMENT_QUESTION, "v2": SENTIMENT_QUESTION_V2}

RESULT_COLUMNS = [
    "review_id",
    "jev_sentiment_v1", "jev_sentiment_v1_confidence",
    "jev_sentiment_v2", "jev_sentiment_v2_confidence",
    "jev_theme", "jev_theme_confidence",
    "jev_model",
]


def ask_jev(df: pd.DataFrame) -> pd.DataFrame:
    """Ask Jev about every review it hasn't answered yet. Returns all answers."""
    if RESULTS_CSV.exists():
        done = pd.read_csv(RESULTS_CSV, dtype={"review_id": str})
    else:
        done = pd.DataFrame(columns=RESULT_COLUMNS)

    todo = df[~df["review_id"].isin(done["review_id"])]
    print(f"{len(done)} reviews already answered, {len(todo)} to ask Jev about.")
    if todo.empty:
        return done

    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY isn't set in this terminal. Run the `read -s` and `export` steps first.")

    new_rows = []
    tokens_in = tokens_out = 0

    def save():
        new = pd.DataFrame(new_rows, columns=RESULT_COLUMNS)
        all_rows = pd.concat([done, new], ignore_index=True) if len(done) else new
        all_rows.to_csv(RESULTS_CSV, index=False)
        return all_rows

    with TypeSafeClient(model=JEV_MODEL) as client:
        for i, row in enumerate(todo.to_dict("records"), start=1):
            questions = {f"sentiment_{name}": q for name, q in SENTIMENT_VERSIONS.items()}
            if row["is_bad"]:
                questions["theme"] = QUESTION

            try:
                response = client.system_one(state={"review": row["body"]}, questions=questions)
            except TypeSafeError as e:
                # Save what we have, so a re-run carries on from here.
                save()
                sys.exit(f"Jev returned an error on review {row['review_id']}: {e}\n"
                         f"Progress is saved. Fix the problem and run the script again.")

            result = {"review_id": row["review_id"], "jev_model": response.model}
            for name in questions:
                result[f"jev_{name}"] = response.choices[name].choice
                result[f"jev_{name}_confidence"] = round(response.choices[name].confidence, 3)
            new_rows.append(result)

            tokens_in += response.usage.input_tokens
            tokens_out += response.usage.output_tokens
            print(f"  {i:>3}/{len(todo)}  {row['detected_lang']}")

            if i % SAVE_EVERY == 0:
                save()

    print(f"Tokens used in this run: {tokens_in:,} in, {tokens_out:,} out")
    return save()


def sentiment_by_label(m: pd.DataFrame) -> pd.DataFrame:
    """Of the reviews you gave each sentiment, how many did each wording match?"""
    rows = []
    for label in ["positive", "neutral", "negative"]:
        part = m[m["my_sentiment"] == label]
        rows.append({
            "my label": label,
            "reviews": len(part),
            "old wording matched": int((part["jev_sentiment_v1"] == label).sum()),
            "new wording matched": int((part["jev_sentiment_v2"] == label).sum()),
        })
    return pd.DataFrame(rows).set_index("my label")


def sentiment_row(name: str, part: pd.DataFrame) -> dict:
    """One row comparing the two wordings on a group of reviews."""
    row = {"reviews": name, "n": len(part)}
    for version, title in [("v1", "old"), ("v2", "new")]:
        s = score(part["my_sentiment"], part[f"jev_sentiment_{version}"])
        row[f"{title} wording"] = f"{s['agreement']} ({s['kappa']})"
    return row


def compare(df: pd.DataFrame, jev: pd.DataFrame, include_all: bool = False) -> str:
    """Work out the numbers for each weak spot. Returns the report as Markdown text."""
    groups = pd.read_csv(GROUPS_CSV, dtype=str)
    m = df.merge(groups, on="review_id", how="left").merge(jev, on="review_id", how="left")

    # A review you marked as the wrong language is left out, as in the first test.
    left_out = int((m["lang_ok"] == "no").sum())
    m = m[m["lang_ok"] != "no"]

    # These labels weren't made independently, so they don't count as hand labels.
    not_independent = m["no"].astype(int).isin(NOT_INDEPENDENT)
    n_not_independent = int(not_independent.sum())
    if include_all:
        independence_note = f"Includes {n_not_independent} labels suggested by AI (reviews {NOT_INDEPENDENT})."
    else:
        m = m[~not_independent]
        independence_note = f"Reviews left out because they weren't independently labelled: {n_not_independent}"

    # Sentiment: the rare_theme group is left out of the side-by-side tables,
    # because Jev helped choose those reviews.
    fair = m[m["group"] != "rare_theme"]
    japanese = fair[fair["detected_lang"] == "ja"]
    sentiment = pd.DataFrame([
        sentiment_row("all randomly picked", fair),
        sentiment_row("mixed (3-4 stars)", fair[fair["group"] == "mixed"]),
        sentiment_row("Japanese", japanese),
    ]).set_index("reviews")

    # German themes: randomly picked 1-2 star reviews.
    german = m[m["group"] == "german_bad"]
    g = score(german["my_theme"], german["jev_theme"])

    # Rare themes: of the reviews Jev gave a rare theme, how many did you agree with?
    rare = m[m["group"] == "rare_theme"]
    rare_rows = []
    for theme, part in rare.groupby("jev_theme"):
        rare_rows.append({
            "Jev's theme": theme,
            "reviews": len(part),
            "you agreed": int((part["my_theme"] == theme).sum()),
        })
    rare_table = pd.DataFrame(rare_rows, columns=["Jev's theme", "reviews", "you agreed"]).set_index("Jev's theme")

    # The same count after the re-checked labels. These were changed after
    # seeing Jev's answers, so the first score above stays the headline.
    rechecks = pd.read_csv(RECHECKS_CSV, dtype=str)
    new_label = dict(zip(rechecks["review_id"], rechecks["rechecked_theme"]))
    rechecked = rare["review_id"].map(new_label).fillna(rare["my_theme"])
    bypass = rare["jev_theme"] == "too_easy_to_bypass"
    n_bypass = int((rechecked[bypass] == "too_easy_to_bypass").sum())

    # Keep every disagreement so you can read why they differ.
    frames = []
    for measure, data, my_col in [("sentiment_v1", m, "my_sentiment"),
                                  ("sentiment_v2", m, "my_sentiment"),
                                  ("theme", m[m["is_bad"]], "my_theme")]:
        differs = data[data[my_col] != data[f"jev_{measure}"]]
        frames.append(pd.DataFrame({
            "review_id": differs["review_id"],
            "measure": measure,
            "group": differs["group"],
            "language": differs["detected_lang"],
            "mine": differs[my_col],
            "jev": differs[f"jev_{measure}"],
            "jev_confidence": differs[f"jev_{measure}_confidence"],
            "notes": differs["notes"],
            "body": differs["body"],
            "body_en": differs["body_en"],
        }))
    disagreements = pd.concat(frames, ignore_index=True).sort_values("jev_confidence", ascending=False)
    disagreements.to_csv(DISAGREEMENTS_CSV, index=False, encoding="utf-8-sig")

    lines = [
        "# Issue #31 – Retest of Jev's weak spots",
        "",
        f"_Run on {date.today():%d %b %Y} · model `{', '.join(sorted(jev['jev_model'].dropna().unique()))}` · {len(m)} reviews_",
        "",
        f"Reviews left out because you marked the language as wrong: {left_out}",
        independence_note,
        "",
        "These reviews are weighted towards the weak spots, so these numbers",
        "can't be compared directly with the first test's overall figures.",
        "",
        "## Sentiment: how often each wording matched each label",
        "",
        to_markdown(sentiment_by_label(fair)),
        "",
        "## Sentiment: agreement, with kappa in brackets",
        "",
        to_markdown(sentiment),
        "",
        "## German themes (1-2 stars)",
        "",
        f"Agreement {g['agreement']}, kappa {g['kappa']}, on {g['reviews']} reviews.",
        "",
        "## Rare themes",
        "",
        "Jev helped choose these reviews, so this only shows how often it's right",
        "when it picks these themes, not how many it misses.",
        "",
        to_markdown(rare_table),
        "",
        f"After re-checking {len(rechecks)} labels under the blocking rule, you agreed with "
        f"{n_bypass} of {int(bypass.sum())} `too_easy_to_bypass` picks.",
        "They were re-checked after seeing Jev's answers, so this score is likely optimistic.",
        "",
        f"All {len(disagreements)} disagreements are in `{DISAGREEMENTS_CSV.name}`, most confident first.",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Retest Jev's weak spots on new reviews.")
    parser.add_argument("--include-all", action="store_true",
                        help="also count the labels that weren't made independently, and say so in the report")
    args = parser.parse_args()

    df = load_labels(LABELS_XLSX)
    print(f"Loaded {len(df)} labelled reviews from {LABELS_XLSX}")

    jev = ask_jev(df)

    report = compare(df, jev, include_all=args.include_all)
    print()
    print(report)
    print()
    print(f"Saved: {RESULTS_CSV.name}, {DISAGREEMENTS_CSV.name} (in {LABELS_DIR})")


if __name__ == "__main__":
    main()
