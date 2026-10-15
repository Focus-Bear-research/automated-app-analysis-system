"""
scripts/smoke_check.py  -  checks used by scripts/smoke_run.sh   (issue #8)

A pipeline stage can "succeed" (no crash) and still produce wrong or empty
output. These checks look INSIDE the output files to catch that.

HOW IT IS USED (smoke_run.sh calls it; you can also run it yourself):
    python scripts/smoke_check.py clean     data/smoke/curated
    python scripts/smoke_check.py outputs   data/smoke/curated
    python scripts/smoke_check.py dashboard data/smoke/curated

Each check prints what it found and exits with code 0 (pass) or 1 (fail).
"""

import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The fixture apps that the cleaning rules SHOULD drop (see
# tests/fixtures/smoke/README.md). Every other fixture app should be kept.
EXPECTED_DROPPED = {"play:co.bitbakery.BrainFit", "ios:id6760403444"}

# Output files that must exist and have at least one row after the run.
# These are the files the dashboard (app.py) reads.
REQUIRED_OUTPUTS = [
    "apps_all.csv",
    "apps_clean.csv",
    "reviews.csv",
    "reviews_with_sentiment.csv",
    "features_llm.csv",
    "features_long.csv",
    "features_summary.csv",
    "features_matrix_flags.csv",
    "DATASET_SUMMARY.md",
]


def fail(message: str) -> None:
    """Print a failure message and stop with exit code 1 (= failed)."""
    print(f"  FAIL: {message}")
    sys.exit(1)


def check_clean(curated: Path) -> None:
    """Did the cleaning step keep and drop the RIGHT apps?"""
    kept = set(pd.read_csv(curated / "apps_clean.csv")["app_key"])
    dropped = set(pd.read_csv(curated / "apps_dropped.csv")["app_key"])

    # "&" between two sets = the items that are in BOTH.
    wrongly_kept = EXPECTED_DROPPED & kept
    if wrongly_kept:
        fail(f"these apps should have been dropped but were kept: {sorted(wrongly_kept)}")

    # "-" between two sets = items in the first set but not the second.
    wrongly_dropped = dropped - EXPECTED_DROPPED
    if wrongly_dropped:
        fail(f"these apps should have been kept but were dropped: {sorted(wrongly_dropped)}")

    print(f"  OK: kept {len(kept)} apps, dropped {len(dropped)} (as expected)")


def check_outputs(curated: Path) -> None:
    """Does every required output file exist and contain data?"""
    for name in REQUIRED_OUTPUTS:
        path = curated / name
        if not path.exists():
            fail(f"missing output file: {name}")
        if path.suffix == ".csv":
            rows = len(pd.read_csv(path))
            if rows == 0:
                fail(f"{name} exists but has no rows")
            print(f"  OK: {name:32} {rows:>5} rows")
        else:
            print(f"  OK: {name}")

    # Extra sanity check: every review should have been given a sentiment label.
    scored = pd.read_csv(curated / "reviews_with_sentiment.csv")
    label_cols = [c for c in scored.columns if "sentiment" in c.lower()]
    if not label_cols:
        fail("reviews_with_sentiment.csv has no sentiment column")
    print(f"  OK: sentiment columns present: {label_cols}")


def check_dashboard(curated: Path) -> None:
    """Open every page of the Streamlit dashboard and check none of them crash.

    Streamlit's AppTest runs app.py "headless" (no browser window) and lets
    us click through the sidebar like a user would.
    """
    from streamlit.testing.v1 import AppTest

    # Tell app.py to read the smoke data instead of data/curated.
    os.environ["CURATED_DIR"] = str(curated.resolve())
    # "streamlit run" lets app.py import files next to it (survivorship_analysis.py);
    # AppTest doesn't, so we add the project folder to Python's search path.
    sys.path.insert(0, str(PROJECT_ROOT))

    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=120)
    app.run()
    if app.exception:
        fail(f"dashboard crashed on first load: {app.exception[0].value}")

    # The sidebar radio button is the page menu. Visit each page in turn.
    pages = app.sidebar.radio[0].options
    problems = []
    for page in pages:
        app.sidebar.radio[0].set_value(page).run()
        if app.exception:
            problems.append(f"{page}: {app.exception[0].value}")
            print(f"  FAIL: page '{page}'")
        else:
            print(f"  OK: page '{page}'")

    if problems:
        fail("some dashboard pages crashed:\n    " + "\n    ".join(problems))


# --- Choose which check to run, based on the command-line words -------
if __name__ == "__main__":
    # sys.argv is the list of words typed after "python":
    #   ["scripts/smoke_check.py", "clean", "data/smoke/curated"]
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    check_name, curated_dir = sys.argv[1], Path(sys.argv[2])

    checks = {"clean": check_clean, "outputs": check_outputs, "dashboard": check_dashboard}
    if check_name not in checks:
        sys.exit(f"Unknown check '{check_name}'. Use one of: {', '.join(checks)}")
    checks[check_name](curated_dir)
