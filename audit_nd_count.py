"""Independent audit of the verified neurodivergent review count.

verify_nd_count.py produces the number. This script checks that number is
trustworthy: no duplicate reviews, categories that add up, every row genuinely
matching a neurodivergent term, and the target status. Run it after
verify_nd_count.py.
"""
import ast
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
from scrapers.reviews_pipeline import get_nd_categories

TARGET = 5000
SRC = 'data/curated/nd_verified.csv'

d = pd.read_csv(SRC, low_memory=False)
d['title'] = d['title'].fillna('')
d['body'] = d['body'].fillna('')
total = len(d)

print('=' * 62)
print('NEURODIVERGENT REVIEW COUNT - INDEPENDENT AUDIT')
print('=' * 62)
print(f'Source file : {SRC}')
print(f'Rows        : {total:,}')
print()

# ---- 1. duplication -------------------------------------------------
print('1. DUPLICATION CHECKS')
with_id = d[d['review_id'].notna()]
dup_ids = int(with_id['review_id'].duplicated().sum())
dup_rows = int(d.duplicated().sum())
d['fp'] = d['app_id'].astype(str) + '||' + (d['title'] + ' ' + d['body']).str.strip().str.lower()
dup_text = int(d['fp'].duplicated().sum())

print(f'   rows carrying a review_id        : {len(with_id):,}')
print(f'   duplicate review_ids             : {dup_ids:,}   {"OK" if dup_ids == 0 else "PROBLEM"}')
print(f'   exact duplicate rows             : {dup_rows:,}   {"OK" if dup_rows == 0 else "PROBLEM"}')
print(f'   same app + same text (lowercased): {dup_text:,}')
if dup_text:
    print('     -> inspect these; identical short phrases written by different')
    print('        users are legitimate, genuine re-ingestion is not')
print()

# ---- 2. categories ---------------------------------------------------
print('2. CATEGORY INTEGRITY')
d['nd'] = d['nd_categories'].apply(ast.literal_eval)
a = d['nd'].apply(lambda c: 'adhd' in c)
u = d['nd'].apply(lambda c: 'autism' in c)
o = d['nd'].apply(lambda c: 'other_nd' in c)
adhd_only = int((a & ~u).sum())
aut_only = int((u & ~a).sum())
both = int((a & u).sum())
other_only = int((o & ~a & ~u).sum())
summed = adhd_only + aut_only + both + other_only

print(f'   ADHD only                        : {adhd_only:,}')
print(f'   Autism only                      : {aut_only:,}')
print(f'   Both ADHD and autism             : {both:,}')
print(f'   Other ND only                    : {other_only:,}')
print(f'   {"-" * 52}')
print(f'   Sum of categories                : {summed:,}')
print(f'   Matches row count                : {"OK" if summed == total else "PROBLEM"}')
print(f'   Rows with no category at all     : {int(d["nd"].apply(len).eq(0).sum()):,}   '
      f'{"OK" if int(d["nd"].apply(len).eq(0).sum()) == 0 else "PROBLEM"}')
print()

# ---- 3. re-label from scratch ---------------------------------------
print('3. RE-LABEL FROM SCRATCH (does every row still qualify?)')
relabel = [bool(get_nd_categories(t, b)) for t, b in zip(d['title'], d['body'])]
bad = total - sum(relabel)
print(f'   rows that still match a ND term  : {sum(relabel):,}')
print(f'   rows that no longer match        : {bad:,}   {"OK" if bad == 0 else "PROBLEM"}')
print()

# ---- 4. target -------------------------------------------------------
print('4. TARGET')
print(f'   Verified neurodivergent reviews  : {total:,}')
print(f'   Target                           : {TARGET:,}')
print(f'   Progress                         : {total / TARGET * 100:.0f}%')
print(f'   Status                           : {"TARGET MET" if total >= TARGET else "below target"}')
print()
print('=' * 62)
