#!/usr/bin/env bash
# =====================================================================
# scripts/smoke_run.sh  -  quick test of every pipeline stage   (issue #8)
# =====================================================================
# WHAT IS A SMOKE RUN?
#   The full pipeline takes about an hour. This runs the SAME code on a
#   tiny fixed dataset (8 apps, 50 reviews, in tests/fixtures/smoke/), so
#   you find out in a few minutes whether anything is broken.
#   ("Smoke test" comes from electronics: switch it on, check nothing
#   starts smoking.)
#
# HOW TO RUN IT (from the project folder, after scripts/setup.sh):
#   bash scripts/smoke_run.sh            # offline: no internet, no API key
#   bash scripts/smoke_run.sh --online   # also test the live scrapers (needs internet)
#   bash scripts/smoke_run.sh --llm      # also call the real LLM for 8 apps
#                                        # (needs OPENAI_API_KEY, costs a few cents)
#
# SAFE: it only writes to data/smoke/. Your real data/curated is untouched.
#
# To look at the result in the dashboard afterwards:
#   CURATED_DIR=data/smoke/curated .venv/bin/streamlit run app.py
# =====================================================================

# Stop on errors and on unset variables (see scripts/setup.sh for details).
set -euo pipefail
cd "$(dirname "$0")/.."      # always run from the project folder

# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------
PY=".venv/bin/python"                 # the project's own Python (made by setup.sh)
FIXTURES="tests/fixtures/smoke"       # the tiny input data (saved in git)
SMOKE="data/smoke"                    # where this run writes its output
OUT="$SMOKE/curated"                  # like data/curated, but for the smoke run

# Read the options typed after the script name, e.g. "--online".
ONLINE=false
LLM=false
for arg in "$@"; do                   # "$@" = all the words after the script name
  case "$arg" in
    --online) ONLINE=true ;;
    --llm)    LLM=true ;;
    *) echo "Unknown option: $arg  (use --online and/or --llm)"; exit 2 ;;
  esac
done

# Check setup.sh has been run, and give a helpful message if not.
if [ ! -x "$PY" ]; then
  echo "ERROR: $PY not found. Run the setup first:   bash scripts/setup.sh"
  exit 1
fi


# ---------------------------------------------------------------------
# The step() helper: runs one stage, times it, and stops on failure
# ---------------------------------------------------------------------
# Usage:  step "Name shown on screen"  command  arguments...
# It prints START / OK / FAILED lines and remembers each result for the
# summary table at the end.
SUMMARY=""                            # grows one line per step
START_ALL=$SECONDS                    # $SECONDS = seconds since the script started

step() {
  local name="$1"; shift              # first word is the name; "shift" removes it,
                                      # so "$@" is now just the command to run
  echo
  echo "---------- START: $name ----------"
  local t0=$SECONDS
  if "$@"; then                       # run the command; true if it succeeded
    local took=$((SECONDS - t0))
    echo "---------- OK: $name (${took}s) ----------"
    SUMMARY+="  OK      ${took}s	$name"$'\n'
  else
    local code=$?                     # $? = the exit code of the failed command
    echo "---------- FAILED: $name (exit code $code) ----------"
    SUMMARY+="  FAILED  	$name"$'\n'
    printf "\nSUMMARY\n%s" "$SUMMARY"
    echo
    echo "SMOKE RUN FAILED at: $name"
    echo "Scroll up to the first error message. See README > Troubleshooting."
    exit 1                            # stop here: later stages need this one's output
  fi
}

# Some stages are skipped in offline mode; this records that in the summary.
skip() {
  echo; echo "---------- SKIP: $1 ----------"
  SUMMARY+="  SKIP    	$1"$'\n'
}


# ---------------------------------------------------------------------
# 0. Start from a clean, empty output folder
# ---------------------------------------------------------------------
echo "Smoke run: online=$ONLINE llm=$LLM  ($($PY --version))"
rm -rf "$SMOKE"                       # delete the previous smoke output (only data/smoke!)
mkdir -p "$SMOKE/input" "$OUT"
cp "$FIXTURES/full_dump.jsonl" "$SMOKE/input/full_dump.jsonl"


# ---------------------------------------------------------------------
# 1-2. Discovery and store scrape
# ---------------------------------------------------------------------
# The real discovery + scrape takes ~1 hour and reads scrapers/seeds.yml,
# so it is not part of the smoke run. The fixture's full_dump.jsonl is a
# saved copy of what that stage produces for our 8 apps.
skip "1-2. discovery + store scrape (too slow; fixture full_dump.jsonl used instead)"


# ---------------------------------------------------------------------
# 3. Normalize: raw JSON records -> one tidy table (apps_all.csv)
# ---------------------------------------------------------------------
step "3. normalize" \
  "$PY" etl/normalize_apps.py --in "$SMOKE/input/full_dump.jsonl" --out "$OUT/apps_all.csv"


# ---------------------------------------------------------------------
# 4. Clean: keep relevant, popular apps; drop the rest
# ---------------------------------------------------------------------
# The thresholds match the defaults in scripts/refresh_all.py.
step "4. clean" \
  "$PY" -m etl.clean_apps --in "$OUT/apps_all.csv" \
    --out "$OUT/apps_clean.csv" --out-dropped "$OUT/apps_dropped.csv" \
    --min-rating-count 25 --min-play-installs 50000 --min-cws-users 10000 --min-relevance 0.15

# Did it keep/drop the apps we expect? (2 fixture apps are meant to be dropped)
step "4b. check cleaning result" "$PY" scripts/smoke_check.py clean "$OUT"


# ---------------------------------------------------------------------
# 5. Websites: fetch each app's homepage text
# ---------------------------------------------------------------------
if [ "$ONLINE" = true ]; then
  # --max 2: only fetch 2 websites, to keep it quick and polite.
  step "5. scrape websites (live, 2 sites)" \
    "$PY" -m etl.scrape_websites --apps "$OUT/apps_clean.csv" --out "$OUT/websites.csv" \
      --max 2 --sleep 0.5
else
  cp "$FIXTURES/websites.csv" "$OUT/websites.csv"
  skip "5. scrape websites (offline: fixture websites.csv used)"
fi


# ---------------------------------------------------------------------
# 6. Reviews: download store reviews for each kept app
# ---------------------------------------------------------------------
if [ "$ONLINE" = true ]; then
  # 10 reviews per app from Australia only, to keep it quick.
  step "6. scrape reviews (live, 10 per app)" \
    "$PY" -m scrapers.reviews_pipeline all --in "$OUT/apps_clean.csv" --out-csv "$OUT/reviews.csv" \
      --stores play,ios --countries au --langs en --max-per-app 10 --since-days 365 --overwrite
else
  cp "$FIXTURES/reviews.csv" "$OUT/reviews.csv"
  skip "6. scrape reviews (offline: fixture reviews.csv used)"
fi


# ---------------------------------------------------------------------
# 7. Sentiment: label each review Positive / Mixed / Negative (RoBERTa)
# ---------------------------------------------------------------------
# The first time, this downloads the RoBERTa model (~500 MB) and needs
# internet. After that the model is cached in ~/.cache/huggingface.
step "7. sentiment (RoBERTa)" \
  "$PY" -m llm.sentiment_pipeline --in "$OUT/reviews.csv" \
    --out "$OUT/reviews_with_sentiment.csv" --backend roberta


# ---------------------------------------------------------------------
# 8. Feature flags: keyword-based feature detection (no LLM)
# ---------------------------------------------------------------------
step "8. feature flags (keywords)" \
  "$PY" -m llm.feature_flags --feature all --apps "$OUT/apps_clean.csv" \
    --web "$OUT/websites.csv" --reviews "$OUT/reviews_with_sentiment.csv" --out-dir "$OUT"


# ---------------------------------------------------------------------
# 9. LLM feature extraction
# ---------------------------------------------------------------------
if [ "$LLM" = true ]; then
  # Real API call for the kept fixture apps: costs a few cents.
  # "${OPENAI_API_KEY:-}" means "the key, or empty text if it is not set".
  if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "ERROR: --llm needs OPENAI_API_KEY. Set it with:  export OPENAI_API_KEY=\"sk-...\""
    exit 1
  fi
  step "9. LLM features (live API)" \
    "$PY" -m llm.feature_llm --apps "$OUT/apps_clean.csv" --web "$OUT/websites.csv" \
      --reviews "$OUT/reviews_with_sentiment.csv" --out "$OUT/features_llm.csv"
else
  # --dry builds every prompt but does NOT call the API. This still tests
  # the prompt-building code for free. We hide its long output (> /dev/null)
  # because it prints every prompt in full.
  step "9. LLM features (dry run: prompts built, no API call)" \
    bash -c "'$PY' -m llm.feature_llm --dry --apps '$OUT/apps_clean.csv' --web '$OUT/websites.csv' \
      --reviews '$OUT/reviews_with_sentiment.csv' --out '$OUT/features_llm_dry.csv' > /dev/null"
  # Then use the saved LLM answers so the next steps have real input.
  cp "$FIXTURES/features_llm.csv" "$OUT/features_llm.csv"
fi


# ---------------------------------------------------------------------
# 10. Feature matrix: combine everything into app x feature tables
# ---------------------------------------------------------------------
step "10. feature matrix" \
  "$PY" -m etl.build_feature_matrix --in-dir "$OUT" --out-dir "$OUT" \
    --llm-csv "$OUT/features_llm.csv" --bundle-apps --apps-csv "$OUT/apps_clean.csv"


# ---------------------------------------------------------------------
# 11. Dataset summary (issue #11)
# ---------------------------------------------------------------------
step "11. dataset summary" \
  "$PY" scripts/dataset_summary.py --curated-dir "$OUT" --no-charts


# ---------------------------------------------------------------------
# 12. Check the outputs and the dashboard
# ---------------------------------------------------------------------
step "12a. check output files" "$PY" scripts/smoke_check.py outputs "$OUT"
step "12b. open every dashboard page" "$PY" scripts/smoke_check.py dashboard "$OUT"


# ---------------------------------------------------------------------
# Done: print the summary table
# ---------------------------------------------------------------------
printf "\nSUMMARY\n%s" "$SUMMARY"
echo
echo "SMOKE RUN PASSED in $((SECONDS - START_ALL))s. Output is in $OUT/"
echo "View it:  CURATED_DIR=$OUT .venv/bin/streamlit run app.py"
