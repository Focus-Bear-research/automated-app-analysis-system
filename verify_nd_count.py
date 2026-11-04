import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')  # so emojis in reviews don't crash printing on Windows
import os
import pandas as pd
from scrapers.reviews_pipeline import get_nd_categories

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
]

print('Loading review files...')
frames = []
for f in files:
    if not os.path.exists(f):          # skip any file that hasn't been scraped yet
        print(f'  {f}: not found, skipping')
        continue
    d = pd.read_csv(f, low_memory=False)
    keep = [c for c in ['review_id', 'app_id', 'title', 'body', 'rating', 'store'] if c in d.columns]
    frames.append(d[keep])
    print(f'  {f}: {len(d):,} rows')

all_r = pd.concat(frames, ignore_index=True)
all_r['title'] = all_r['title'].fillna('')
all_r['body'] = all_r['body'].fillna('')

# Deduplicate: by review_id where available, otherwise by app + review text
print('\nDeduplicating...')
has_id = all_r[all_r['review_id'].notna()].drop_duplicates(subset='review_id')
no_id = all_r[all_r['review_id'].isna()].copy()
no_id['k'] = no_id['app_id'].astype(str) + '||' + (no_id['title'] + ' ' + no_id['body']).str.strip().str.lower()
no_id = no_id.drop_duplicates(subset='k').drop(columns='k')
combined = pd.concat([has_id, no_id], ignore_index=True)

# A title repeated 3+ times for the same app is the app's name, not a review title
repeats = combined.groupby(['app_id', 'title'])['title'].transform('size')
combined['title'] = combined['title'].where(repeats < 3, '')

# Label every review
print('Labelling reviews (this takes a couple of minutes)...\n')
combined['nd_categories'] = combined.apply(lambda r: get_nd_categories(r['title'], r['body']), axis=1)

adhd = combined['nd_categories'].apply(lambda c: 'adhd' in c).sum()
autism = combined['nd_categories'].apply(lambda c: 'autism' in c).sum()
both = combined['nd_categories'].apply(lambda c: 'adhd' in c and 'autism' in c).sum()
other = combined['nd_categories'].apply(lambda c: 'other_nd' in c).sum()
adhd_or_autism = combined['nd_categories'].apply(lambda c: 'adhd' in c or 'autism' in c).sum()
any_nd = combined['nd_categories'].apply(len).gt(0).sum()

print('=' * 55)
print('NEURODIVERGENT REVIEW COUNT — VERIFIED')
print('=' * 55)
print(f'Total unique reviews analysed : {len(combined):,}')
print(f'ADHD-labelled                 : {adhd:,}')
print(f'Autism-labelled               : {autism:,}')
print(f'Both ADHD and autism          : {both:,}')
print(f'Other neurodivergent          : {other:,}')
print(f'ADHD or autism                : {adhd_or_autism:,}')
print('-' * 55)
print(f'TOTAL NEURODIVERGENT REVIEWS  : {any_nd:,}')
print(f'ND rate                       : {any_nd/len(combined)*100:.2f}%')
print('=' * 55)

labeled = combined[combined['nd_categories'].apply(len) > 0]

# Which apps are producing the ND reviews
print('\nTop 10 apps by ND review count:')
top = labeled.groupby('app_id').size().sort_values(ascending=False).head(10)
for app, n in top.items():
    print(f'  {app:<45} {n:,}')

# Sample evidence, so the number can be spot-checked by hand
print('\nSample ND reviews (verify these are genuine):')
for _, r in labeled.head(5).iterrows():
    txt = str(r['body'])[:110].replace('\n', ' ')
    print(f"  [{r['nd_categories']}] {txt}...")

labeled.to_csv('data/curated/nd_verified.csv', index=False)
print(f'\nSaved {len(labeled):,} verified reviews to data/curated/nd_verified.csv')
