Automated App Analysis System

1. PROJECT STRUCTURE

  automated-app-analysis-system/
  |
  +-- scrapers/
  |   +-- scrape_pipeline.py
  |   +-- reviews_pipeline.py
  |   +-- store_play.py
  |   +-- store_ios.py
  |   +-- store_cws.py
  |   +-- discovery/
  |   |   +-- search_play.py
  |   |   +-- search_ios.py
  |   |   +-- search_cws.py
  |   +-- seeds.yml
  |   +-- discovery.yml
  |
  +-- etl/
  |   +-- normalize_apps.py
  |   +-- clean_apps.py
  |   +-- scrape_websites.py
  |   +-- build_app_cards.py
  |   +-- aggregate_review_insights.py
  |   +-- build_feature_matrix.py
  |   +-- validate_lyngs_classification.py
  |
  +-- llm/
  |   +-- sentiment_pipeline.py
  |   +-- feature_llm.py
  |   +-- feature_extract.py
  |   +-- feature_flags.py
  |   +-- taxonomy.yml
  |
  +-- scripts/
  |   +-- improved_sentiment_analysis.py
  |   +-- adhd_sentiment_analysis.py
  |   +-- adhd_theme_detection.py
  |   +-- llm_adhd_classifier.py
  |
  +-- data/
  |   +-- input/
  |   +-- curated/
  |       +-- apps_all_clean.csv
  |       +-- reviews.csv
  |       +-- reviews_with_sentiment.csv
  |       +-- reviews_with_ml_sentiment.csv
  |       +-- adhd_reviews_analysis.csv
  |       +-- adhd_theme_analysis.csv
  |       +-- llm_adhd_behaviour_analysis.csv
  |       +-- app_metrics.csv
  |       +-- features_llm.csv
  |       +-- features_matrix_flags.csv
  |       +-- features_matrix_confidence.csv
  |       +-- features_matrix_review_hits.csv
  |       +-- lyngs_validation_groundtruth.csv
  |
  +-- survivorship_analysis.py
  +-- app.py
  +-- README.md

2. SETUP (fresh clone -> working dashboard)

2.1 What you need first

  - Python 3.12. NOT 3.13: on 3.13, torch cannot be installed on Intel Macs and greenlet
    (needed by playwright) fails to build. On a Mac:  brew install python@3.12
  - git, and about 3 GB of free disk space (torch and the sentiment models are large).

2.2 One-command setup

    git clone https://github.com/Focus-Bear-research/automated-app-analysis-system.git
    cd automated-app-analysis-system
    bash scripts/setup.sh

setup.sh finds Python 3.12, creates a virtual environment in .venv/, installs the pinned
versions in requirements.txt, installs the Chromium browser for playwright, and creates the
data folders. It is safe to run again.

2.3 Check it works: the smoke run (a few minutes)

    bash scripts/smoke_run.sh

This runs every pipeline stage on a tiny fixed dataset (8 apps, 50 reviews, saved in
tests/fixtures/smoke/) and writes only to data/smoke/, so your real data is not touched.
It ends with "SMOKE RUN PASSED" or tells you which stage failed. Options:

    bash scripts/smoke_run.sh --online   # also test the live website and review scrapers
    bash scripts/smoke_run.sh --llm      # also call the real LLM (needs OPENAI_API_KEY, a few cents)

To see the smoke data in the dashboard:

    CURATED_DIR=data/smoke/curated .venv/bin/streamlit run app.py

Run the smoke run after every code change, before opening a pull request.
To change which apps are in the test set, edit scripts/make_smoke_fixtures.py and run it.

2.4 Open the dashboard on the real data

    .venv/bin/streamlit run app.py

2.5 Use the project's Python

Run every command below with the project's Python, either by typing .venv/bin/python
instead of python, or by first "activating" the environment in your Terminal:

    source .venv/bin/activate

2.6 API key (only for the LLM steps)

    export OPENAI_API_KEY="sk-..."          # Mac / Linux, lasts until you close the Terminal
    $env:OPENAI_API_KEY = "sk-..."          # Windows PowerShell

Never commit the key to git. See section 7 for cost and run time.

3. PIPELINE WALKTHROUGH

All commands are run from the project root.

Step 1 -- App Discovery & Scraping

Discovers and scrapes app metadata from seeds defined in seeds.yml and discovery.yml.

    python -m scrapers.scrape_pipeline full --discover

Step 2 -- Normalise & Clean

Normalisation is run automatically by Step 1. To run manually:

    python -m etl.normalize_apps --in data/input/full_dump.jsonl --out data/curated/apps_all.csv

    python -m etl.clean_apps --in data/curated/apps_all.csv --out data/curated/apps_clean.csv

    python -m etl.build_feature_matrix --in-dir data/curated --out-dir data/curated

Step 3 -- Scrape Reviews

    python -m scrapers.reviews_pipeline all --in data/curated/apps_clean.csv --out-csv data/curated/reviews.csv --max-per-app 2000 --stores play,ios,cws --countries au,us,gb,ca,nz,ie --langs en --since-days 3650 --overwrite

Use the sweet-spot profiler to calibrate before a full run:

    python -m scrapers.reviews_pipeline sweet-spot `
      --in data/curated/apps_all_clean.csv `
      --sample-apps 5 `
      --caps 200,500,1000,2000

Step 4 -- Sentiment & ADHD Labelling

    python -m llm.sentiment_pipeline --in data/curated/reviews.csv --out data/curated/reviews_with_sentiment.csv --backend roberta --resume

Step 5 -- Aggregate Review Insights

    python -m etl.aggregate_review_insights --reviews data/curated/reviews_with_sentiment.csv --apps data/curated/apps_clean.csv --out data/curated/app_metrics.csv

Step 6 -- Feature Flags

    # All features at once
    python -m llm.feature_flags `
      --feature all `
      --apps data/curated/apps_clean.csv `
      --reviews data/curated/reviews_with_sentiment.csv `
      --out-dir data/curated/

    # Single feature
    python -m llm.feature_flags `
      --feature adhdsupport `
      --apps data/curated/apps_clean.csv `
      --out data/curated/features_adhdsupport.csv

Step 7 -- Feature Extraction (LLM)

    python -m llm.feature_extract --apps data/curated/apps_clean.csv --out-jsonl data/curated/features.jsonl --out-csv data/curated/features.csv --model openai:gpt-4.1-mini --max-apps 102 --sleep 0.6

Step 8 -- LLM Feature Classification

    python -m llm.feature_llm --apps data/curated/apps_clean.csv --web data/curated/websites.csv --reviews data/curated/reviews.csv --taxonomy llm/taxonomy.yml --out data/curated/features_llm.csv --app-type auto

Step 9 -- Build Feature Matrix

    python -m etl.build_feature_matrix --in-dir data/curated --out-dir data/curated --taxonomy llm/taxonomy.yml --llm-csv data/curated/features_llm.csv --bundle-apps --apps-csv data/curated/apps_all_clean.csv --bundle-sent --sent-csv data/curated/app_metrics.csv

Step 10 -- Validate Lyngs Classification

    python -m etl.validate_lyngs_classification --ground-truth data/curated/lyngs_validation_groundtruth.csv --predictions data/curated/features_llm.csv --out-dir data/curated/validation

Step 11 -- Launch Dashboard

    streamlit run app.py


4. Dashboard Updates

New ADHD-specific components added to app.py:

  ADHD Behavioural Insights
  ADHD Theme Analysis
  Automated ADHD Insight Summary
  ADHD Behavioural Recommendations

The automated insight section reports the most common behavioural themes, secondary themes,
common patterns, and ADHD review statistics without requiring manual review of individual comments.

5. SURVIVORSHIP ANALYSIS

The Survivorship Analysis page (survivorship_analysis.py) uses a 2019 point-in-time review
snapshot from three CSV files:

  2019_03_19-play_reviews_unique.csv    -- Google Play      -- Up to March 2019
  2019-03-21_apple_reviews_unique.csv   -- Apple App Store  -- Up to March 2019
  2019-02-08-chrome_reviews_unique.csv  -- Chrome Web Store -- Up to February 2019

Apps are mapped to the Lyngs (2022) self-regulation app registry and manually verified for
survival status as of May 2026 (Active / Stale / Discontinued).

The page provides:
  Tab 1 -- App status table
  Tab 2 -- Feature mention rates: Active vs Discontinued (% of reviews mentioning each feature bucket)
  Tab 3 -- Average rating trends over time per survival status
  Tab 4 -- Explore individual reviews by app and feature
  Tab 5 -- Methodology and limitations

Key finding: Active apps show ~20% higher mention rates for Reward features and ~5% higher for
ADHD features; Nudge features are ~13% more common in discontinued apps.


6. DASHBOARD PAGES

  Overview
  Competitors
  Sentiment Analysis
  Feature Matrix
  ADHD Analysis
  Summary
  Survivorship Analysis

The Feature Matrix page displays:

  Top Detected Features
  Number of Apps by Feature
  Feature Distribution by App Area
  Feature Counts by App Area
  Apps with the Most Detected Features
  Insights Summary

7. LLM, API KEY, COST AND RUN TIME

7.1 Which model and provider

  Step 8 (llm/feature_llm.py) sends one prompt per app per routed app type (DSCT, habit,
  planner) to OpenAI's Chat Completions API. Default model: gpt-4.1-mini (--model to
  change), temperature 0, up to 3,200 output tokens. --base-url points it at any
  OpenAI-compatible provider. --dry builds the prompts without calling the API (free).

7.2 How the key is supplied

  OPENAI_API_KEY  -- read from the environment (see 2.6), or pass --api-key.
  OPENAI_BASE_URL -- optional, for an OpenAI-compatible provider other than OpenAI.
  Only the LLM steps need a key. refresh_all.py runs the LLM step only with --use-llm.

7.3 Approximate cost and time of a full run (ESTIMATES, measured Oct 2026)

  Size of the last full run: 729 apps -> 2,187 LLM calls (about 3 per app).
  Prompt size, measured with the real prompt code: about 2,200 tokens without website text,
  about 3,200 with it.

  LLM step (gpt-4.1-mini, at about US$0.40 per 1M input tokens and US$1.60 per 1M output):
      input   ~2,187 x 3,000 tokens = ~6.6M tokens  -> ~US$2.60
      output  ~2,187 x 1,000 tokens = ~2.2M tokens  -> ~US$3.50
      total   about US$5-10 per full run; roughly 3-5 hours (about 5-8 s per call)
  Check current prices on OpenAI's pricing page and the real cost on your usage dashboard
  after a run, then update these numbers.

  Non-LLM stages (measured on a 2017 Intel MacBook Pro, logs/e2e_20261002_185705.log):
      discovery + scrape + normalize + clean + websites + reviews ......... ~56 min
      survivorship scraper ................................................ ~10 min
      RoBERTa sentiment and the other scripts ............................. minutes
  Smoke run (scripts/smoke_run.sh): a few minutes; the first run also downloads the
  ~500 MB sentiment model.


8. TROUBLESHOOTING (KNOWN ISSUES & FIXES)

First step for any problem: run  bash scripts/smoke_run.sh  and see which stage fails.

8.1 Setup and installation

  Symptom: "Failed building wheel for greenlet" / "this header requires Py_BUILD_CORE define"
  Cause:   Python 3.13. playwright 1.47 needs greenlet 3.0.x, which does not build on 3.13.
  Fix:     Use Python 3.12 (brew install python@3.12), then: rm -rf .venv && bash scripts/setup.sh

  Symptom: "No matching distribution found for torch"
  Cause:   Python 3.13 on an Intel Mac. torch 2.2.2 is the last Intel Mac version, up to Python 3.12.
  Fix:     As above: use Python 3.12.

  Symptom: "ERROR: Playwright does not support chromium on mac13"
  Cause:   An unpinned, newer playwright was installed (newer versions dropped macOS 13).
  Fix:     Install from requirements.txt (playwright==1.47.0). Only website scraping with
           --js-fallback needs Chromium; everything else works without it.

  Symptom: "NameError: name 'torch' is not defined" (RoBERTa sentiment, zero-shot ADHD classifier)
  Cause:   transformers is installed but torch is not (it failed to install, see above).
  Fix:     Run setup.sh with Python 3.12 so torch installs.

  Symptom: "pyarrow requires NumPy 2.0 or newer, found 1.26.4" (dashboard tables crash)
  Cause:   An unpinned, new pyarrow. numpy must stay at 1.26.x for torch 2.2.2.
  Fix:     Install from requirements.txt (pyarrow==17.0.0).

  Symptom: a stage dies with "SIGSEGV" / "exit -11"
  Cause:   Seen with the old Python 3.13 "venv/" folder (library builds that don't match).
  Fix:     Use the .venv/ that setup.sh makes with Python 3.12.

  Symptom: the first run of any step is very slow (a minute or more for a tiny file)
  Cause:   Normal. A new environment compiles and caches its libraries on first use,
           and the first sentiment run downloads the ~500 MB RoBERTa model.
  Fix:     None needed; later runs are fast.

8.2 Pipeline

  Symptom: refresh_all.py reports success, but outputs are missing or old
  Cause:   With --continue-on-error, refresh_all.py still exits with "OK" when steps fail.
           Read its log for "[ERROR] step failed" lines.

  Symptom: refresh_all.py sentiment step: "unrecognized arguments: run --out-reviews ... --engine vader"
  Cause:   refresh_all.py still uses an old command format. llm/sentiment_pipeline.py now
           takes --in, --out and --backend (roberta or llm), with no "run" subcommand.
  Fix:     NOT FIXED YET. Until it is, run the sentiment step by hand (see Step 4 above).

  Symptom: refresh_all.py feature-matrix step: "unrecognized arguments: --min-review-hits ... --sent-csv"
  Cause:   etl/build_feature_matrix.py no longer has those options.
  Fix:     NOT FIXED YET. Until it is, run Step 9 above by hand.

  Issue: TypeError: Path.replace() takes 2 positional arguments in feature_extract.py line 183
  Fix:   Change out_csv.replace(".csv","_rollup.csv") to
         out_csv.with_name(out_csv.stem + "_rollup.csv")

  Issue: unrecognized arguments: --cap --limit in reviews_pipeline.py
  Fix:   Use --max-per-app instead of --cap; there is no --limit argument -- filter the input
         CSV to limit apps

  Issue: ADHD review count too low
  Fix:   Increase --max-per-app, --since-days, and --countries in the reviews pipeline step

  Issue: Survivorship page not loading
  Fix:   Ensure the three 2019 review CSV files are present in the project root or data/ subfolder

  Issue: Dashboard showing "0.0" or "nan" for rating/installs
  Fix:   Use format_rating() and format_installs() helpers -- see Module 5 above
