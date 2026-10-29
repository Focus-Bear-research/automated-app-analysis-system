# etl/complaint_themes.py
# =====================================================================
# Complaint themes and the Jev question   (issue #25)
# =====================================================================
# One place for the themes, so the agreement test
# (scripts/compare_jev_test_set.py) and the full analysis
# (scripts/analyze_competitor_complaints.py) always ask Jev the same thing.
#
# The descriptions are "version 2": rewritten after reviewing the 28
# disagreements in the first agreement test (mainly: a broken app is
# bugs_crashes, not too_rigid). They match the theme rules in the
# labelling notes. If you change a description here, re-run
# scripts/compare_jev_test_set.py to check agreement again.
# =====================================================================

from typesafe_sdk import Choice

# Exact Jev model, so results don't change when TypeSafe releases a new one.
JEV_MODEL = "jev-1.14.0"

# Below this confidence, the full analysis stores the theme as "uncertain"
# instead of trusting Jev. In the test set, answers at >= 0.5 confidence
# agreed with the hand labels 86% of the time.
MIN_CONFIDENCE = 0.5

# label -> description Jev reads to decide.
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

# The question sent to Jev with each review. Jev must pick exactly one label.
QUESTION = Choice(
    instructions="This is a negative app store review of a productivity or focus app. "
                 "What is the reviewer's MAIN complaint? If there are several, pick the one "
                 "they write the most about or are angriest about.",
    criteria=THEMES,
)
