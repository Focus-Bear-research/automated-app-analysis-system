# data/labels/make_issue31_labelling_sheet.py
# =====================================================================
# Turn the test set into an Excel sheet with dropdowns   (issue #31)
# =====================================================================
# WHAT IS THIS FOR?
#   Typing labels by hand invites typos like "bug_crashes". In this sheet
#   you pick each label from a dropdown, and Excel refuses anything else.
#
# HOW TO RUN IT (from the project folder, after make_issue31_test_set.py):
#   .venv/bin/python data/labels/make_issue31_labelling_sheet.py
#
# SAFE: it never overwrites a sheet you've already started labelling,
# unless you add --force.
# =====================================================================

import argparse
import math
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Let this script import from the project's own folders (e.g. etl/).
sys.path.insert(0, str(PROJECT_ROOT))
from etl.complaint_themes import THEMES  # noqa: E402  (same themes Jev chooses from)

LABELS_DIR = PROJECT_ROOT / "data" / "labels"
TEST_SET_CSV = LABELS_DIR / "issue31_test_set.csv"
OUT_XLSX = LABELS_DIR / "issue31_test_set_labelling.xlsx"
RETEST_CSV = LABELS_DIR / "issue31_retest_set.csv"
RETEST_XLSX = LABELS_DIR / "issue31_retest_labelling.xlsx"

SENTIMENTS = ["positive", "neutral", "negative"]

# Column -> width. Columns to fill in come straight after the review text,
# and the ones you don't need to read are at the far right.
COLUMNS = {
    "no": 5,
    "rating": 7,
    "detected_lang": 9,
    "body": 55,
    "body_en": 55,
    "my_theme": 20,
    "my_sentiment": 14,
    "lang_ok": 9,
    "notes": 30,
    "review_id": 14,
    "app_key": 20,
    "country": 9,
}

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
TO_FILL = PatternFill("solid", fgColor="FFF2CC")      # yellow: fill this in
NOT_NEEDED = PatternFill("solid", fgColor="D9D9D9")   # grey: leave blank


def row_height(texts: list[tuple[str, int]]) -> float:
    """Work out a row height that shows all the wrapped text.

    `texts` is a list of (text, column width). Japanese characters take
    about twice the space of English ones, so they count double.
    """
    most_lines = 1
    for text, width in texts:
        lines = 0
        for part in text.split("\n"):
            size = sum(2 if ord(ch) > 0x2E7F else 1 for ch in part)
            lines += max(1, math.ceil(size / (width - 2)))
        most_lines = max(most_lines, lines)
    return min(409, most_lines * 14 + 4)   # 409 is the tallest row Excel allows


def add_dropdown(sheet, cells: list[str], options: list[str], message: str):
    """Add a dropdown to the cells. Excel rejects anything not in the list."""
    # Excel needs the options as one comma-separated text in quotes.
    rule = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
    rule.showErrorMessage = True
    rule.errorTitle = "Not in the list"
    rule.error = message
    sheet.add_data_validation(rule)
    for cell in cells:
        rule.add(cell)


def build_labels_sheet(sheet, df: pd.DataFrame):
    """The sheet where you do the labelling, one review per row."""
    names = list(COLUMNS)
    sheet.append(names)
    for col, name in enumerate(names, start=1):
        cell = sheet.cell(row=1, column=col)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.column_dimensions[cell.column_letter].width = COLUMNS[name]

    theme_col = sheet.cell(row=1, column=names.index("my_theme") + 1).column_letter
    sentiment_col = sheet.cell(row=1, column=names.index("my_sentiment") + 1).column_letter
    lang_col = sheet.cell(row=1, column=names.index("lang_ok") + 1).column_letter
    theme_cells = []

    for row, r in enumerate(df.to_dict("records"), start=2):
        for col, name in enumerate(names, start=1):
            value = r[name]
            # Store these as numbers so they sort properly.
            if name in ("no", "rating"):
                value = int(value)
            # Reviews are plain text. data_type "s" stops Excel treating one
            # that starts with "=" as a formula.
            cell = sheet.cell(row=row, column=col)
            cell.value = value
            if isinstance(value, str):
                cell.data_type = "s"
            cell.font = Font(name=FONT, size=10)
            cell.alignment = Alignment(vertical="top", wrap_text=True)

        # 1-2 star reviews get a theme. 3-5 star reviews are sentiment only,
        # so their theme cell is grey with no dropdown.
        if int(r["rating"]) <= 2:
            sheet[f"{theme_col}{row}"].fill = TO_FILL
            theme_cells.append(f"{theme_col}{row}")
        else:
            sheet[f"{theme_col}{row}"].fill = NOT_NEEDED
        sheet[f"{sentiment_col}{row}"].fill = TO_FILL

        sheet.row_dimensions[row].height = row_height([
            (r["body"], COLUMNS["body"]),
            (r["body_en"], COLUMNS["body_en"]),
        ])

    last = len(df) + 1
    add_dropdown(sheet, theme_cells, list(THEMES), "Pick a theme from the dropdown.")
    add_dropdown(sheet, [f"{sentiment_col}2:{sentiment_col}{last}"], SENTIMENTS, "Pick a sentiment from the dropdown.")
    add_dropdown(sheet, [f"{lang_col}2:{lang_col}{last}"], ["no"], 'Pick "no" if the language is wrong, otherwise leave it blank.')

    # Keep the header and the review text in view while scrolling, and
    # add filter buttons so you can show only the unfinished rows.
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def build_help_sheet(sheet):
    """A second sheet explaining what to fill in, and what each theme means."""
    rows = [
        ("How to label", None),
        ("Yellow cells", "Fill these in. Click the cell, then pick from the arrow that appears."),
        ("Grey cells", "Leave blank. 3-5 star reviews only need a sentiment."),
        ("my_theme", "The reviewer's MAIN complaint. If there are several, pick the one they write the most about or are angriest about."),
        ("Telling themes apart", "Paying, paywalls and hidden prices: pricing. App stuck or login failing: bugs_crashes. Long or confusing setup: onboarding. Blocking or limits not working, for any reason: too_easy_to_bypass."),
        ("my_sentiment", "How the review reads overall. Go by the words, not the star rating."),
        ("positive", "Only praise, with no clear complaint or request."),
        ("neutral", "Both clear praise and a clear complaint or request. Also a description, question or request with no opinion either way."),
        ("negative", "Mainly complaints, even if they briefly say something nice."),
        ("lang_ok", 'Pick "no" only if the review is not in the language shown in detected_lang.'),
        ("notes", "Optional. Anything you weren't sure about."),
        ("body_en", "An AI translation to help you read the review. Check the original if something seems off."),
        ("", None),
        ("Example (not a real review)", None),
        ("body_en", "It charged me for a year on the first day of the free trial."),
        ("my_theme", "pricing"),
        ("my_sentiment", "negative"),
        ("", None),
        ("Themes", None),
    ] + list(THEMES.items())

    for label, text in rows:
        sheet.append([label, text])
        row = sheet.max_row
        sheet.cell(row=row, column=1).font = Font(name=FONT, size=12 if text is None else 10, bold=True)
        sheet.cell(row=row, column=2).font = Font(name=FONT, size=10)
        sheet.cell(row=row, column=1).alignment = Alignment(vertical="top")
        sheet.cell(row=row, column=2).alignment = Alignment(vertical="top", wrap_text=True)
        if text:
            sheet.row_dimensions[row].height = row_height([(text, 90)])

    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 90


def main():
    parser = argparse.ArgumentParser(description="Make the labelling sheet for issue #31.")
    parser.add_argument("--force", action="store_true", help="overwrite an existing sheet")
    parser.add_argument("--retest", action="store_true", help="make the sheet for the retest set")
    args = parser.parse_args()

    test_set_csv = RETEST_CSV if args.retest else TEST_SET_CSV
    out_xlsx = RETEST_XLSX if args.retest else OUT_XLSX

    # Don't destroy hand labels by accident.
    if out_xlsx.exists() and not args.force:
        sys.exit(f"{out_xlsx} already exists. Not overwriting your labels. "
                 f"Use --force if you really want a new one.")

    if not test_set_csv.exists():
        sys.exit(f"Can't find {test_set_csv}. Make the test set first.")

    # keep_default_na=False: read empty cells as "" instead of NaN.
    df = pd.read_csv(test_set_csv, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df.insert(0, "no", [str(i) for i in range(1, len(df) + 1)])

    workbook = Workbook()
    labels = workbook.active
    labels.title = "Labels"
    build_labels_sheet(labels, df)
    build_help_sheet(workbook.create_sheet("How to label"))

    workbook.save(out_xlsx)
    print(f"Saved {len(df)} reviews to {out_xlsx}")


if __name__ == "__main__":
    main()
