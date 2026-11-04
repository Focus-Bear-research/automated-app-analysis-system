import sys
sys.path.insert(0, '.')  # lets Python find the scrapers folder from here
from scrapers import reviews_pipeline as rp  # the module we want to test

# These tests never touch the network. We swap out the two fetch functions for
# fake ones that fail in the ways the real stores fail, then check that
# fetch_reviews_with_retry notices instead of quietly reporting "no reviews".

ONE_REVIEW = [{'review_id': 'r1', 'body': 'great app'}]  # stand-in for a real result


def fake_sequence(*results):
    """Build a fake fetcher that returns (or raises) each result in turn."""
    calls = {'n': 0}

    def fetcher(*args, **kwargs):
        i = calls['n']
        calls['n'] += 1
        out = results[min(i, len(results) - 1)]  # repeat the last one if asked again
        if isinstance(out, Exception):
            raise out
        return out

    fetcher.calls = calls  # so a test can see how many attempts happened
    return fetcher


def run_case(name, store, play_fake, ios_fake, expect_rows, expect_reason_set):
    # put our fakes in place of the real network calls
    real_play, real_ios = rp.fetch_play_reviews, rp.fetch_ios_reviews
    rp.fetch_play_reviews, rp.fetch_ios_reviews = play_fake, ios_fake
    try:
        # base_wait=0 so the test runs instantly instead of sleeping 30s
        rows, reason = rp.fetch_reviews_with_retry(store, 'com.example', 'au', 'en', 10,
                                                   retries=3, base_wait=0)
    finally:
        rp.fetch_play_reviews, rp.fetch_ios_reviews = real_play, real_ios

    got_rows = len(rows)
    got_reason_set = reason is not None
    ok = (got_rows == expect_rows) and (got_reason_set == expect_reason_set)
    status = 'PASS' if ok else 'FAIL'
    print(f'{status} | {name}')
    print(f'       rows={got_rows} (expected {expect_rows})  reason={reason!r}')
    return ok


no_ios = fake_sequence([])  # used when the case is not about the App Store
no_play = fake_sequence([])  # used when the case is not about Play

results = []

# Play throttling used to look identical to "this app has no reviews". After
# every retry is used up we should get an explanation back, not a silent empty.
results.append(run_case(
    'Play keeps returning empty -> we are told why, not given a silent empty',
    'PlayStore', fake_sequence([], [], []), no_ios,
    expect_rows=0, expect_reason_set=True))

# The case that actually cost us 259 apps: empty first, fine on a later try.
results.append(run_case(
    'Play empty then works -> reviews recovered',
    'PlayStore', fake_sequence([], ONE_REVIEW), no_ios,
    expect_rows=1, expect_reason_set=False))

# A DNS or connection blip used to skip the app for the whole run.
results.append(run_case(
    'Play raises then works -> reviews recovered',
    'PlayStore', fake_sequence(ConnectionError('getaddrinfo failed'), ONE_REVIEW), no_ios,
    expect_rows=1, expect_reason_set=False))

results.append(run_case(
    'Play always raises -> reason names the error',
    'PlayStore', fake_sequence(ConnectionError('getaddrinfo failed')), no_ios,
    expect_rows=0, expect_reason_set=True))

# On the App Store an empty response is believable, so we should accept it
# straight away rather than waiting through pointless retries.
results.append(run_case(
    'App Store empty -> trusted as genuinely no reviews, no retry',
    'AppStore', no_play, fake_sequence([]),
    expect_rows=0, expect_reason_set=False))

print()
print(f'{sum(results)}/{len(results)} passed')
