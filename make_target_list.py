import pandas as pd

# Load the scrape results and work out the ND hit rate per app
scraped = pd.read_csv('data/curated/reviews_full_scrape.csv').drop_duplicates(subset='review_id')
stats = scraped.groupby('app_id').agg(
    total=('review_id', 'count'),
    nd=('special_reviews', lambda s: (s == True).sum())
)
stats['nd_rate'] = stats['nd'] / stats['total'] * 100

# Keep only apps where at least 5% of reviews are neurodivergent-related
good_apps = stats[stats['nd_rate'] >= 5.0].index.tolist()
print('High-ND apps kept:', len(good_apps))
for a in good_apps:
    print('  ', a, f"{stats.loc[a, 'nd_rate']:.1f}%")

# Pull those apps out of the full app list
apps = pd.read_csv('data/curated/apps_clean.csv')
targeted = apps[apps['id'].isin(good_apps)]
targeted.to_csv('data/curated/apps_high_nd.csv', index=False)
print('\nSaved', len(targeted), 'apps to data/curated/apps_high_nd.csv')
