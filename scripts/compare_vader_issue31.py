# scripts/compare_vader_issue31.py
# =====================================================================
# Compare VADER with Jev on the foreign-language test set   (issue #31)
# =====================================================================
# WHAT IS THIS FOR?
#   compare_jev_issue31.py shows how well Jev agrees with the hand labels.
#   This script scores the SAME reviews with VADER, the sentiment method
#   the pipeline uses now, so we can see how much better Jev is.
#
# HOW TO RUN IT (from the project folder, after compare_jev_issue31.py):
#   .venv/bin/python scripts/compare_vader_issue31.py
#
# COST: none. VADER runs on your laptop and doesn't use Jev.
# =====================================================================

import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Let this script import from the project's own folders (e.g. llm/).
sys.path.insert(0, str(PROJECT_ROOT))
# The pipeline's own VADER code, so the score cut-offs are the real ones.
from llm.sentiment_pipeline import VaderEngine, clean_text  # noqa: E402
from scripts.compare_jev_issue31 import LABELS_DIR, RESULTS_CSV, VERSIONS, load_labels, score  # noqa: E402
from scripts.compare_jev_test_set import to_markdown  # noqa: E402

VADER_RESULTS_CSV = LABELS_DIR / "issue31_vader_results.csv"


def score_with_vader(df: pd.DataFrame) -> pd.DataFrame:
    """Score both versions of every review. Returns one row per review and version."""
    engine = VaderEngine()
    rows = []
    for row in df.to_dict("records"):
        for version, column in VERSIONS.items():
            # Body only, the same text Jev was given.
            compound, label = engine.score(clean_text(row[column]))
            rows.append({
                "review_id": row["review_id"],
                "version": version,
                "vader_compound": compound,
                "vader_sentiment": label,
            })
    return pd.DataFrame(rows)


def build_report(m: pd.DataFrame) -> str:
    """Work out VADER's and Jev's numbers side by side. Returns Markdown text."""
    rows = []
    for lang in ["all"] + sorted(m["detected_lang"].unique()):
        in_lang = m if lang == "all" else m[m["detected_lang"] == lang]
        row = {"language": lang}
        for version in VERSIONS:
            part = in_lang[in_lang["version"] == version]
            for method in ["vader", "jev"]:
                s = score(part["my_sentiment"], part[f"{method}_sentiment"])
                row[f"{method} {version}"] = f"{s['agreement']} ({s['kappa']})"
        rows.append(row)
    table = pd.DataFrame(rows).set_index("language")

    # A compound of exactly 0 means VADER found no word it knows (or the
    # words cancelled out), so the review gets called neutral by default.
    original = m[m["version"] == "original"]
    translated = m[m["version"] == "translated"]

    lines = [
        "# Issue #31 – VADER vs Jev on sentiment",
        "",
        "Each cell is % agreement with the hand labels, with kappa in brackets.",
        "",
        to_markdown(table),
        "",
        "## How often VADER scored exactly 0",
        "",
        f"- Original text: {(original['vader_compound'] == 0).mean():.0%} of {len(original)} reviews",
        f"- English translation: {(translated['vader_compound'] == 0).mean():.0%} of {len(translated)} reviews",
        "",
        "## Negative reviews VADER caught",
        "",
        "Of the reviews you labelled negative, how many each method also called negative:",
        "",
    ]
    for version in VERSIONS:
        part = m[(m["version"] == version) & (m["my_sentiment"] == "negative")]
        vader = (part["vader_sentiment"] == "negative").sum()
        jev = (part["jev_sentiment"] == "negative").sum()
        lines.append(f"- {version}: VADER {vader} of {len(part)}, Jev {jev} of {len(part)}")
    return "\n".join(lines)


def main():
    df = load_labels()
    vader = score_with_vader(df)
    vader.to_csv(VADER_RESULTS_CSV, index=False)

    jev = pd.read_csv(RESULTS_CSV, dtype={"review_id": str})
    m = df.merge(vader, on="review_id").merge(jev, on=["review_id", "version"])

    # A review you marked as the wrong language doesn't count, as in the Jev report.
    m = m[m["lang_ok"] != "no"]

    print(build_report(m))
    print()
    print(f"Saved: {VADER_RESULTS_CSV.name} (in {LABELS_DIR})")


if __name__ == "__main__":
    main()
