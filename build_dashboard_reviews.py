import sys
sys.path.insert(0, '.')
import os
import pandas as pd
from scrapers.reviews_pipeline import is_special_review

# Every file that contains scraped reviews
files = [
    'data/curated/reviews_full_scrape.csv',
    'data/curated/reviews_high_nd.csv',
    'data/curated/all_reviews_export.csv',
    'data/curated/reviews_round2.csv',
    'data/curated/reviews_nd_apps.csv',
    'data/curated/reviews_round3.csv',
    'data/curated/reviews_ios.csv',
    'data/curated/reviews_play_retry.csv',
    # Gunnam's iOS scrape: 129k reviews, 74 apps, 18 countries. Note this is
    # ios_reviews.csv, NOT the reviews_ios.csv above (which was never run).
    'data/curated/ios_reviews.csv',
]

# Columns the dashboard's ADHD Analysis page needs
cols = ['app_key', 'store', 'app_id', 'country', 'lang', 'review_id',
        'user_name', 'rating', 'title', 'body', 'version', 'at']

print('Loading review files...')
frames = []
for f in files:
    if not os.path.exists(f):          # skip any file that hasn't been scraped yet
        print(f'  {f}: not found, skipping')
        continue
    d = pd.read_csv(f, low_memory=False)
    frames.append(d[[c for c in cols if c in d.columns]])

all_r = pd.concat(frames, ignore_index=True)
all_r['title'] = all_r['title'].fillna('')
all_r['body'] = all_r['body'].fillna('')

# Make review_id text before de-duplicating. Some files store it as a number
# (ios_reviews.csv) and others as text, and after concat the number
# 10059510025 and the string '10059510025' look like two different reviews, so
# the same review survives the de-duplication twice.
def _norm_review_id(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s.endswith('.0'):          # a numeric id that pandas read as a float
        s = s[:-2]
    return s or None

all_r['review_id'] = all_r['review_id'].map(_norm_review_id)

# Remove duplicates: by review_id when we have one, otherwise by app + text
has_id = all_r[all_r['review_id'].notna()].drop_duplicates(subset='review_id')
no_id = all_r[all_r['review_id'].isna()].copy()
no_id['k'] = no_id['app_id'].astype(str) + '||' + (no_id['title'] + ' ' + no_id['body']).str.strip().str.lower()
no_id = no_id.drop_duplicates(subset='k').drop(columns='k')
combined = pd.concat([has_id, no_id], ignore_index=True)

# A title repeated 3+ times for the same app is the app's name - don't scan it
repeats = combined.groupby(['app_id', 'title'])['title'].transform('size')
clean_title = combined['title'].where(repeats < 3, '')

print('Flagging neurodivergent reviews (takes a few minutes)...')
combined['special_reviews'] = [is_special_review(t, b) for t, b in zip(clean_title, combined['body'])]

combined.to_csv('data/curated/reviews.csv', index=False)
print(f"Wrote {len(combined):,} reviews to data/curated/reviews.csv")
print(f"Flagged as neurodivergent: {combined['special_reviews'].sum():,}")
