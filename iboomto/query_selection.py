"""Select a small, explainable union from GSC's bounded query responses."""
from datetime import timedelta
from .core import LAUNCH

POOL_LIMIT = 5000
TOP_METRIC = 100
TOP_OPPORTUNITY = 50
VERSION = 'query-opportunities-v1'


def baseline_range(start, end, period):
    previous_end = start - timedelta(days=1)
    if period == 'daily':
        return start-timedelta(days=7), previous_end
    if period == 'monthly':
        return previous_end.replace(day=1), previous_end
    return start-(end-start)-timedelta(days=1), previous_end


def select(current, baseline, current_days, baseline_days, baseline_status):
    current = {r['query']: r for r in current}
    previous = {r['query']: r for r in baseline}
    reasons = {}
    def add(rows, reason, limit):
        for r in rows[:limit]:
            reasons.setdefault(r['query'], []).append(reason)
    add(sorted(current.values(), key=lambda r: (-r['clicks'], -r['impressions'], r['query'])), 'top100_clicks', TOP_METRIC)
    add(sorted(current.values(), key=lambda r: (-r['impressions'], -r['clicks'], r['query'])), 'top100_impressions', TOP_METRIC)
    growth = {}
    if baseline_status == 'available':
        new = [r for q,r in current.items() if q not in previous and r['impressions']/current_days >= 10]
        add(sorted(new, key=lambda r: (-r['impressions'], r['query'])), 'new_in_candidate_pool', TOP_OPPORTUNITY)
        for q,r in current.items():
            old = previous.get(q)
            if not old or old['impressions'] <= 0:
                continue
            now_rate, old_rate = r['impressions']/current_days, old['impressions']/baseline_days
            delta, ratio = now_rate-old_rate, now_rate/old_rate-1
            if now_rate >= 20 and delta >= 10 and ratio >= .5:
                growth[q] = (delta, ratio)
        add(sorted((current[q] for q in growth), key=lambda r: (-growth[r['query']][0], r['query'])), 'growing_impressions', TOP_OPPORTUNITY)
    result = []
    for q, selected_by in reasons.items():
        old = previous.get(q) if baseline_status == 'available' else None
        row = {**current[q], 'selection_reason': '|'.join(selected_by),
               'baseline_status': baseline_status if baseline_status != 'available' else 'returned' if old else 'not_returned_in_pool',
               'baseline_clicks': old['clicks'] if old else '', 'baseline_impressions': old['impressions'] if old else '',
               'impressions_daily_delta': '', 'impressions_growth_ratio': ''}
        if old and old['impressions'] > 0:
            rate = current[q]['impressions']/current_days; previous_rate = old['impressions']/baseline_days
            row.update(impressions_daily_delta=rate-previous_rate, impressions_growth_ratio=rate/previous_rate-1)
        result.append(row)
    return result


def collect_queries(api, start, end, period, lang, exact='', prefix='', cache=None):
    cache = cache if cache is not None else {}
    def pool(s,e):
        key = (s,e,lang,exact,prefix)
        if key not in cache:
            cache[key] = api.gsc(s,e,['query'],lang,'final',exact,prefix,limit=POOL_LIMIT)
        return cache[key]
    rows, info, cap = pool(start,end)
    bs,be = baseline_range(start,end,period)
    baseline=[];baseline_cap=False;status='insufficient_history'
    # Partial launch periods cannot establish first appearance or reliable growth.
    if bs >= LAUNCH and start >= LAUNCH:
        baseline,_,baseline_cap=pool(bs,be)
        status='available' if baseline else 'no_baseline_rows'
    chosen=select(rows,baseline,(end-start).days+1,(be-bs).days+1,status)
    for row in chosen:
        row.update(baseline_start=str(bs),baseline_end=str(be),candidate_pool_size=len(rows),
                   candidate_pool_limit=POOL_LIMIT,candidate_pool_truncated=cap or len(rows)>=POOL_LIMIT,
                   baseline_pool_truncated=baseline_cap or len(baseline)>=POOL_LIMIT,
                   query_selection_version=VERSION)
    return chosen,info
