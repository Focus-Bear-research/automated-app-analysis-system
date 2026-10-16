#!/usr/bin/env bash
# =====================================================================
# scripts/setup.sh  -  one-command setup for a fresh clone   (issue #8)
# =====================================================================
# WHAT IT DOES
#   1. Finds Python 3.12 on your computer.
#   2. Creates a "virtual environment" (.venv): a private folder of
#      Python libraries just for this project, so it can't clash with
#      other projects on your laptop.
#   3. Installs the exact library versions listed in requirements.txt.
#   4. Downloads the headless Chromium browser that playwright uses.
#   5. Creates the data folders the pipeline expects.
#
# HOW TO RUN IT (from the project folder, in Terminal):
#   bash scripts/setup.sh
#
# It is safe to run again: steps that are already done are skipped.
# =====================================================================

# "set -euo pipefail" makes the script stop at the first error, instead of
# carrying on and producing confusing problems later.
#   -e  stop if any command fails
#   -u  stop if we use a variable that was never set (catches typos)
#   -o pipefail  a failure in "cmd1 | cmd2" counts as a failure
set -euo pipefail

# Move into the project root folder (the parent of this scripts/ folder),
# so the script works no matter which folder you run it from.
cd "$(dirname "$0")/.."

VENV_DIR=".venv"          # where the virtual environment will live
WANTED_PY="3.12"          # the Python version this project is tested on

# A small helper that prints a coloured heading, so the output is easy to scan.
say() { printf "\n\033[1;34m==> %s\033[0m\n" "$1"; }


# ---------------------------------------------------------------------
# Step 1: find Python 3.12
# ---------------------------------------------------------------------
say "Step 1/5: looking for Python $WANTED_PY"

# "command -v X" prints the path of program X if it exists, or nothing.
# We try "python3.12" first, then plain "python3" in case it is 3.12.
PYTHON=""
for candidate in "python$WANTED_PY" python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    # Ask that Python what version it is, e.g. "3.12"
    version=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [ "$version" = "$WANTED_PY" ]; then
      PYTHON="$candidate"
      break
    fi
  fi
done

# "-z" means "is this text empty?". If we didn't find Python 3.12, stop
# with clear instructions instead of failing halfway through.
if [ -z "$PYTHON" ]; then
  echo "ERROR: Python $WANTED_PY was not found."
  echo "  On a Mac with Homebrew, install it with:   brew install python@$WANTED_PY"
  echo "  Python 3.13 will NOT work (torch and greenlet fail to install)."
  exit 1
fi
echo "Using $PYTHON ($("$PYTHON" --version))"


# ---------------------------------------------------------------------
# Step 2: create the virtual environment
# ---------------------------------------------------------------------
say "Step 2/5: creating the virtual environment in $VENV_DIR/"

# "-d" means "does this folder exist?". The "!" flips it to "does NOT exist".
if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON" -m venv "$VENV_DIR"
  echo "Created $VENV_DIR/"
else
  echo "$VENV_DIR/ already exists, reusing it."
fi

# From here on we use the venv's own Python. Anything we install goes into
# .venv/ rather than into your system Python.
VENV_PY="$VENV_DIR/bin/python"

# Safety check: an old .venv might have been made with a different Python.
venv_version=$("$VENV_PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$venv_version" != "$WANTED_PY" ]; then
  echo "ERROR: $VENV_DIR/ uses Python $venv_version, but $WANTED_PY is needed."
  echo "  Delete it and run this script again:   rm -rf $VENV_DIR && bash scripts/setup.sh"
  exit 1
fi


# ---------------------------------------------------------------------
# Step 3: install the libraries
# ---------------------------------------------------------------------
say "Step 3/5: installing libraries from requirements.txt (first time: several minutes)"

# Upgrade pip (the installer) first, because old pips can fail on new packages.
"$VENV_PY" -m pip install --upgrade pip --quiet
"$VENV_PY" -m pip install -r requirements.txt


# ---------------------------------------------------------------------
# Step 4: download the headless browser for playwright
# ---------------------------------------------------------------------
say "Step 4/5: installing the Chromium browser for playwright"

# Only the website-scraping step uses this, and only for JavaScript-heavy
# sites. So if it fails we print a WARNING and keep going instead of stopping.
# "if ! cmd" runs the block when the command FAILS.
if ! "$VENV_PY" -m playwright install chromium; then
  echo "WARNING: Chromium could not be installed. Everything else still works;"
  echo "  only 'scrape_websites --js-fallback' needs it. See README > Troubleshooting."
fi


# ---------------------------------------------------------------------
# Step 5: create the data folders
# ---------------------------------------------------------------------
say "Step 5/5: creating data folders"

# "mkdir -p" creates a folder, and does nothing if it already exists.
mkdir -p data/input data/curated logs
echo "data/input, data/curated and logs are ready."


# ---------------------------------------------------------------------
# Done: tell the user what to do next
# ---------------------------------------------------------------------
say "Setup finished"
cat <<'EOF'
Next steps:
  1. Check everything works (a few minutes, uses tiny test data):
       bash scripts/smoke_run.sh
  2. Open the dashboard:
       .venv/bin/streamlit run app.py
  3. (Optional) For the LLM feature step, set your OpenAI key in this Terminal:
       export OPENAI_API_KEY="sk-..."
EOF
