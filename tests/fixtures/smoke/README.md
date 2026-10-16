# Smoke-test fixture data

Tiny, fixed test data used by `scripts/smoke_run.sh` (issue #8).
Re-create it with `.venv/bin/python scripts/make_smoke_fixtures.py`.

| File | Rows | What it is |
|---|---|---|
| full_dump.jsonl | 8 | raw scraped app records (input to normalize) |
| reviews.csv | 50 | real reviews, 10 per app, mixed stars, some mention ADHD/focus |
| websites.csv | 8 | website columns only; text left empty so the run works offline |
| features_llm.csv | 126 | saved LLM feature answers, so no API key is needed |

## Apps and why each is included

| app_key | Why |
|---|---|
| `play:cc.forestapp` | Google Play, DSCT focus app, many reviews |
| `play:co.thefabulous.app` | Google Play, habit tracker |
| `play:com.gmail.jmartindev.timetune` | Google Play, planner |
| `ios:id1480220328` | App Store, planner marketed for ADHD (Tiimo) |
| `ios:id1478345385` | App Store, focus timer with few reviews |
| `cws:ifdepgnnjpnbkcgempionjablajancjc` | Chrome Web Store, site blocker, NO reviews (edge case) |
| `play:co.bitbakery.BrainFit` | SHOULD BE DROPPED by cleaning: weak scope |
| `ios:id6760403444` | SHOULD BE DROPPED by cleaning: too few ratings |
