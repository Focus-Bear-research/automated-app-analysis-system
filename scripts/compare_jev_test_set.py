# scripts/compare_jev_test_set.py
# =====================================================================
# Run Jev on the hand-labelled test set and measure agreement   (issue #25)
# =====================================================================
# WHAT IS THIS FOR?
#   Jeremy: "label a test set of reviews manually before doing any Jev
#   classifications and see if there's good agreement."
#   This script sends each test review to Jev, puts Jev's answer next to
#   the hand label, and works out how often they agree.
#
# HOW TO RUN IT (from the project folder, in a terminal where you've set
# the key with `read -s` + `export TYPESAFE_API_KEY`):
#   .venv/bin/python scripts/compare_jev_test_set.py
#
# IT CAN BE STOPPED AND RESTARTED: answers are saved as it goes, and a
# re-run only asks Jev about reviews it hasn't answered yet. So a crash
# or Ctrl+C never costs you money twice.
#
# COST: about 700 tokens per review, so ~70,000 tokens for 100 reviews.
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
LABELS_DIR = PROJECT_ROOT / "data" / "labels"

TEST_SET_CSV = LABELS_DIR / "issue25_test_set.csv"        # your hand labels (input)
RESULTS_CSV = LABELS_DIR / "issue25_jev_results.csv"      # Jev's answers (output, also the cache)
REPORT_MD = LABELS_DIR / "issue25_agreement_report.md"    # the summary for Jeremy (output)

# Fix the exact Jev model, so results don't change when TypeSafe
# releases a new one. (try_jev.py showed jev-1.14.0 on 22 Oct 2026.)
JEV_MODEL = "jev-1.14.0"

# Same themes and descriptions (version 2) as try_jev.py and the theme rules in
# PY_issue25_next_steps.md. If you change the rules, change them here too.
THEMES = {
    "pricing": "Too expensive, a paywall, subscription, billing or refund problems (surprise charges, can't cancel), a free version that's too limited, the price is hidden until after setup, or barriers put there to make users pay.",
    "bugs_crashes": "The app is broken: it crashes, freezes, is slow, gives wrong results, or a feature doesn't work as it should. Includes being locked out or unable to log in or reach their content because the app is failing.",
    "too_easy_to_bypass": "Blocking or limits leak for any reason: the user can get around them, or some apps or sites are not actually blocked or stopped when they should be.",
    "too_rigid": "The app's rules are too strict on purpose: it blocks things the person needs, has no way out in an emergency, or won't let them change or turn off a block. Includes kids complaining that parental controls restrict them. NOT when the app is broken or failing (that is bugs_crashes).",
    "notifications": "Too many, too few, or annoying phone notifications or reminders. Not pop-ups inside the app.",
    "onboarding": "Problems when first setting up or signing up: confusing setup, can't register, stuck on a setup step, needs an invite code, or hard to learn at first.",
    "sync": "Data, purchases or accounts don't carry across devices: no sync between devices, data lost when switching, or problems after getting a new phone or resetting the phone.",
    "missing_feature": "They wanted something the app doesn't have.",
    "other": "None of the above, e.g. ads, can't uninstall, pop-ups asking for a rating, design, or not really a complaint.",
}

QUESTION = Choice(
    instructions="This is a negative app store review of a productivity or focus app. "
                 "What is the reviewer's MAIN complaint? If there are several, pick the one "
                 "they write the most about or are angriest about.",
    criteria=THEMES,
)

# Save progress to disk after this many reviews.
SAVE_EVERY = 10


def load_test_set() -> pd.DataFrame:
    """Read the hand labels and stop with a clear message if anything is wrong."""
    if not TEST_SET_CSV.exists():
        sys.exit(f"Can't find {TEST_SET_CSV}. Run scripts/make_issue25_test_set.py and label it first.")

    # keep_default_na=False: read empty cells as "" instead of NaN.
    df = pd.read_csv(TEST_SET_CSV, dtype=str, keep_default_na=False)

    unlabelled = df[df["my_label"].str.strip() == ""]
    if len(unlabelled):
        sys.exit(f"{len(unlabelled)} reviews have no my_label yet. Finish labelling first.")

    # Catch typos like "bug_crashes", which would count as a disagreement.
    bad = sorted(set(df["my_label"]) - set(THEMES))
    if bad:
        sys.exit(f"These labels aren't in the theme list (check the spelling): {bad}")

    return df


def ask_jev(df: pd.DataFrame) -> pd.DataFrame:
    """Send every review Jev hasn't answered yet. Returns all of Jev's answers."""
    # Load answers from an earlier run, if there is one (the "cache").
    if RESULTS_CSV.exists():
        done = pd.read_csv(RESULTS_CSV, dtype={"review_id": str})
    else:
        done = pd.DataFrame(columns=["review_id", "jev_label", "jev_confidence", "jev_model"])

    todo = df[~df["review_id"].isin(done["review_id"])]
    print(f"{len(done)} reviews already answered, {len(todo)} to ask Jev about.")
    if todo.empty:
        return done

    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY isn't set in this terminal. Run the `read -s` and `export` steps first.")

    new_rows = []

    def save():
        # Add the new answers to the old ones and write the file.
        all_rows = pd.concat([done, pd.DataFrame(new_rows)], ignore_index=True)
        all_rows.to_csv(RESULTS_CSV, index=False)
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
                "jev_label": answer.choice,
                "jev_confidence": round(answer.confidence, 3),
                "jev_model": response.model,
            })
            print(f"  {i:>3}/{len(todo)}  {answer.choice:<20} {answer.confidence:.2f}")

            if i % SAVE_EVERY == 0:
                save()

    return save()


def cohen_kappa(a: pd.Series, b: pd.Series) -> float:
    """Cohen's kappa: agreement after taking away the agreement you'd get by luck.

    observed = how often a and b agree.
    expected = how often they'd agree if both just picked labels at random,
               each using their own mix of labels (e.g. if both say "pricing"
               25% of the time, they'd agree on pricing 0.25 x 0.25 by luck).
    kappa    = (observed - expected) / (1 - expected)
    """
    observed = (a == b).mean()
    a_share = a.value_counts(normalize=True)
    b_share = b.value_counts(normalize=True)
    expected = (a_share * b_share).sum()     # labels only one side used count as 0
    return (observed - expected) / (1 - expected)


def to_markdown(table: pd.DataFrame) -> str:
    """Turn a small table into a Markdown table (so we don't need an extra package)."""
    header = [table.index.name or ""] + [str(c) for c in table.columns]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    # itertuples keeps each column's type (iterrows would turn 28 into 28.0).
    for idx, row in zip(table.index, table.itertuples(index=False)):
        lines.append("| " + " | ".join([str(idx)] + [str(v) for v in row]) + " |")
    return "\n".join(lines)


def compare(df: pd.DataFrame, jev: pd.DataFrame) -> str:
    """Work out the agreement numbers. Returns the report as Markdown text."""
    m = df.merge(jev, on="review_id", how="left")
    m["agree"] = m["my_label"] == m["jev_label"]
    n = len(m)

    # % agreement: how often Jev picked the same label as you.
    agreement = m["agree"].mean()

    # Cohen's kappa: 1 = perfect, 0 = no better than chance.
    # Rough guide: 0.6-0.8 good, above 0.8 very good.
    kappa = cohen_kappa(m["my_label"], m["jev_label"])

    # Per theme: of the reviews YOU gave this label, how many did Jev also give it?
    per_theme = (m.groupby("my_label")["agree"].agg(["count", "sum"])
                   .rename(columns={"count": "my_reviews", "sum": "jev_agrees"}))
    per_theme["agreement"] = (per_theme["jev_agrees"] / per_theme["my_reviews"]).round(2)
    per_theme = per_theme.sort_values("my_reviews", ascending=False)

    # Confusion table: rows = your label, columns = Jev's label.
    # Big numbers off the diagonal show which themes get mixed up.
    confusion = pd.crosstab(m["my_label"], m["jev_label"])

    # Does low confidence predict disagreement? If yes, we can treat
    # low-confidence answers as "uncertain" later.
    conf_agree = m.loc[m["agree"], "jev_confidence"].median()
    conf_disagree = m.loc[~m["agree"], "jev_confidence"].median()

    disagreements = m.loc[~m["agree"], ["review_id", "app_key", "my_label", "jev_label",
                                        "jev_confidence", "notes", "body"]]
    disagreements = disagreements.sort_values("jev_confidence", ascending=False)
    disagreements.to_csv(LABELS_DIR / "issue25_disagreements.csv", index=False)

    lines = [
        "# Issue #25 – Jev vs test-set labels",
        "",
        f"_Run on {date.today():%d %b %Y} · model `{', '.join(sorted(jev['jev_model'].dropna().unique()))}` · {n} reviews_",
        "",
        "## Headline",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| % agreement | {agreement:.0%} ({m['agree'].sum()} of {n}) |",
        f"| Cohen's kappa | {kappa:.2f} |",
        f"| Median Jev confidence when it agrees | {conf_agree:.2f} |",
        f"| Median Jev confidence when it disagrees | {conf_disagree:.2f} |",
        "",
        "Kappa guide: 0.6–0.8 good, above 0.8 very good.",
        "",
        "## Agreement per theme (by test-set label)",
        "",
        to_markdown(per_theme),
        "",
        "## Confusion table (rows = test-set label, columns = Jev)",
        "",
        to_markdown(confusion),
        "",
        f"All {len(disagreements)} disagreements are in `issue25_disagreements.csv`, most confident first.",
    ]
    return "\n".join(lines)


def main():
    df = load_test_set()
    print(f"Loaded {len(df)} labelled reviews from {TEST_SET_CSV}")

    jev = ask_jev(df)

    report = compare(df, jev)
    REPORT_MD.write_text(report + "\n")
    print()
    print(report)
    print()
    print(f"Saved: {RESULTS_CSV.name}, {REPORT_MD.name}, issue25_disagreements.csv (in {LABELS_DIR})")


if __name__ == "__main__":
    main()
