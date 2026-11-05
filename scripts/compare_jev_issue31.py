# scripts/compare_jev_issue31.py
# =====================================================================
# Test Jev on foreign-language reviews   (issue #31)
# =====================================================================
# WHAT IS THIS FOR?
#   Does Jev work on reviews that aren't in English? This script sends
#   each hand-labelled review to Jev twice, and compares its answers with
#   your labels, language by language:
#     - "original":   the review as it was written
#     - "translated": the AI translation into English (body_en)
#   Comparing the two shows whether we'd need to translate reviews first.
#
#   It asks Jev up to three questions per review:
#     - theme:     the main complaint (1-2 star reviews only, because the
#                  question tells Jev it's reading a negative review)
#     - sentiment: positive, neutral or negative (every review)
#     - language:  which language it's in (original version only)
#
# HOW TO RUN IT (from the project folder, in a terminal where you've set
# the key with `read -s` + `export TYPESAFE_API_KEY`):
#   .venv/bin/python scripts/compare_jev_issue31.py
#
# IT CAN BE STOPPED AND RESTARTED: answers are saved as it goes, and a
# re-run only asks Jev about reviews it hasn't answered yet. So a crash
# or Ctrl+C never costs you money twice.
#
# COST: 300 requests (150 reviews, 2 versions). The tokens used are
# printed at the end.
# =====================================================================

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
# Same themes, question and model as #25, so the results can be compared.
from etl.complaint_themes import JEV_MODEL, QUESTION, THEMES  # noqa: E402
from scripts.compare_jev_test_set import cohen_kappa, to_markdown  # noqa: E402

LABELS_DIR = PROJECT_ROOT / "data" / "labels"

LABELS_XLSX = LABELS_DIR / "issue31_test_set_labelling.xlsx"   # your hand labels (input)
RESULTS_CSV = LABELS_DIR / "issue31_jev_results.csv"           # Jev's answers (output, also the cache)
DISAGREEMENTS_CSV = LABELS_DIR / "issue31_disagreements.csv"   # every answer that differs from your label

# Save progress to disk after this many requests.
SAVE_EVERY = 10

# Which text column each version of the review comes from.
VERSIONS = {"original": "body", "translated": "body_en"}

SENTIMENT_QUESTION = Choice(
    instructions="This is an app store review. What is the reviewer's overall sentiment about the app?",
    criteria={
        "positive": "Mostly happy with the app, even if they mention a small problem.",
        "neutral": "Neither happy nor unhappy, a balanced mix, or just a request or description.",
        "negative": "Mostly unhappy with the app.",
    },
)

LANGUAGE_QUESTION = Choice(
    instructions="Which language is this review mainly written in?",
    criteria={
        "de": "German",
        "pt": "Portuguese",
        "fr": "French",
        "es": "Spanish",
        "ja": "Japanese",
        "en": "English",
        "other": "Any other language.",
    },
)

RESULT_COLUMNS = [
    "review_id", "version",
    "jev_theme", "jev_theme_confidence",
    "jev_sentiment", "jev_sentiment_confidence",
    "jev_language", "jev_language_confidence",
    "jev_model",
]


def load_labels(path: Path = LABELS_XLSX) -> pd.DataFrame:
    """Read the hand labels and stop with a clear message if anything is wrong."""
    if not path.exists():
        sys.exit(f"Can't find {path}. Run data/labels/make_issue31_labelling_sheet.py and label it first.")

    # keep_default_na=False: read empty cells as "" instead of NaN.
    df = pd.read_excel(path, sheet_name="Labels", dtype=str, keep_default_na=False)
    for col in ["my_theme", "my_sentiment", "lang_ok"]:
        df[col] = df[col].str.strip()
    df["is_bad"] = df["rating"].astype(int) <= 2

    # Check everything is filled in before spending any money.
    no_theme = df[df["is_bad"] & (df["my_theme"] == "")]
    no_sentiment = df[df["my_sentiment"] == ""]
    if len(no_theme) or len(no_sentiment):
        sys.exit(f"Finish labelling first: {len(no_theme)} reviews need my_theme "
                 f"and {len(no_sentiment)} need my_sentiment.")

    # The dropdowns stop typos, but pasted values get past them.
    bad_labels = sorted((set(df["my_theme"]) - {""}) - set(THEMES))
    bad_labels += sorted(set(df["my_sentiment"]) - set(SENTIMENT_QUESTION.criteria))
    if bad_labels:
        sys.exit(f"These labels aren't in the dropdown lists (check the spelling): {bad_labels}")

    return df


def ask_jev(df: pd.DataFrame) -> pd.DataFrame:
    """Ask Jev about every review and version it hasn't answered yet. Returns all answers."""
    # Load answers from an earlier run, if there is one (the "cache").
    if RESULTS_CSV.exists():
        done = pd.read_csv(RESULTS_CSV, dtype={"review_id": str})
    else:
        done = pd.DataFrame(columns=RESULT_COLUMNS)
    already = set(zip(done["review_id"], done["version"]))

    todo = [(row, version) for row in df.to_dict("records") for version in VERSIONS
            if (row["review_id"], version) not in already]
    print(f"{len(already)} requests already answered, {len(todo)} to ask Jev about.")
    if not todo:
        return done

    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY isn't set in this terminal. Run the `read -s` and `export` steps first.")

    new_rows = []
    tokens_in = tokens_out = 0

    def save():
        # Add the new answers to the old ones and write the file.
        new = pd.DataFrame(new_rows, columns=RESULT_COLUMNS)
        all_rows = pd.concat([done, new], ignore_index=True) if len(done) else new
        all_rows.to_csv(RESULTS_CSV, index=False)
        return all_rows

    with TypeSafeClient(model=JEV_MODEL) as client:
        for i, (row, version) in enumerate(todo, start=1):
            questions = {"sentiment": SENTIMENT_QUESTION}
            if row["is_bad"]:
                questions["theme"] = QUESTION
            if version == "original":
                questions["language"] = LANGUAGE_QUESTION

            try:
                response = client.system_one(
                    state={"review": row[VERSIONS[version]]},
                    questions=questions,
                )
            except TypeSafeError as e:
                # Save what we have, so a re-run carries on from here.
                save()
                sys.exit(f"Jev returned an error on review {row['review_id']}: {e}\n"
                         f"Progress is saved. Fix the problem and run the script again.")

            answers = response.choices
            result = {"review_id": row["review_id"], "version": version, "jev_model": response.model}
            for name in questions:
                result[f"jev_{name}"] = answers[name].choice
                result[f"jev_{name}_confidence"] = round(answers[name].confidence, 3)
            new_rows.append(result)

            tokens_in += response.usage.input_tokens
            tokens_out += response.usage.output_tokens
            print(f"  {i:>3}/{len(todo)}  {version:<10} {row['detected_lang']}  {answers['sentiment'].choice}")

            if i % SAVE_EVERY == 0:
                save()

    print(f"Tokens used in this run: {tokens_in:,} in, {tokens_out:,} out")
    return save()


def score(mine: pd.Series, jev: pd.Series) -> dict:
    """Work out agreement and kappa for one group of reviews."""
    agree = mine == jev
    # Kappa can't be worked out when both sides used one label for everything.
    both_one_label = pd.concat([mine, jev]).nunique() < 2
    return {
        "reviews": len(mine),
        "agreement": f"{agree.mean():.0%}",
        "kappa": "n/a" if both_one_label else f"{cohen_kappa(mine, jev):.2f}",
    }


def score_table(m: pd.DataFrame, my_col: str, jev_col: str) -> pd.DataFrame:
    """One row per language, plus an "all" row, with one set of columns per version."""
    rows = []
    for lang in ["all"] + sorted(m["detected_lang"].unique()):
        in_lang = m if lang == "all" else m[m["detected_lang"] == lang]
        row = {"language": lang}
        for version in VERSIONS:
            part = in_lang[in_lang["version"] == version]
            scores = score(part[my_col], part[jev_col])
            row["reviews"] = scores["reviews"]
            row[f"{version} agreement"] = scores["agreement"]
            row[f"{version} kappa"] = scores["kappa"]
        rows.append(row)
    return pd.DataFrame(rows).set_index("language")


def compare(df: pd.DataFrame, jev: pd.DataFrame) -> str:
    """Work out the agreement numbers. Returns the report as Markdown text."""
    m = df.merge(jev, on="review_id", how="left")

    # A review you marked as the wrong language doesn't belong in that
    # language's numbers, so it's left out of them.
    wrong_lang = m[m["lang_ok"] == "no"]
    m = m[m["lang_ok"] != "no"]

    themes = m[m["is_bad"]]
    original = m[m["version"] == "original"]

    # Keep every disagreement so you can read why they differ.
    frames = []
    for measure, data, my_col in [("theme", themes, "my_theme"), ("sentiment", m, "my_sentiment")]:
        differs = data[data[my_col] != data[f"jev_{measure}"]]
        frames.append(pd.DataFrame({
            "review_id": differs["review_id"],
            "measure": measure,
            "version": differs["version"],
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

    language_right = (original["jev_language"] == original["detected_lang"]).mean()

    lines = [
        "# Issue #31 – Jev vs hand labels on foreign-language reviews",
        "",
        f"_Run on {date.today():%d %b %Y} · model `{', '.join(sorted(jev['jev_model'].dropna().unique()))}`_",
        "",
        f"Reviews left out because you marked the language as wrong: {len(wrong_lang) // len(VERSIONS)}",
        "",
        "## Theme (1-2 star reviews)",
        "",
        to_markdown(score_table(themes, "my_theme", "jev_theme")),
        "",
        "## Sentiment (all reviews)",
        "",
        to_markdown(score_table(m, "my_sentiment", "jev_sentiment")),
        "",
        "## Language",
        "",
        f"Jev named the same language as langdetect on {language_right:.0%} of {len(original)} reviews.",
        "",
        "Kappa guide: 0.6–0.8 good, above 0.8 very good.",
        "With about 20 reviews per language, one review moves a theme score by 5 points,",
        "so small gaps between languages don't mean much.",
        "",
        f"All {len(disagreements)} disagreements are in `{DISAGREEMENTS_CSV.name}`, most confident first.",
    ]
    return "\n".join(lines)


def main():
    df = load_labels()
    print(f"Loaded {len(df)} labelled reviews from {LABELS_XLSX}")

    jev = ask_jev(df)

    report = compare(df, jev)
    print()
    print(report)
    print()
    print(f"Saved: {RESULTS_CSV.name}, {DISAGREEMENTS_CSV.name} (in {LABELS_DIR})")


if __name__ == "__main__":
    main()
