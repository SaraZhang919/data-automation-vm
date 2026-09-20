"""Keep historical findings without presenting them as freshly verified incidents."""
from .sf_freshness import fresh_date, fresh_batches, is_sf_issue, report_issue_allowed

INACTIVE = {'resolved', 'historical', 'needs_recheck'}

def current_issue(row, store, now=None):
    if row.get('state') in INACTIVE:
        return False
    if is_sf_issue(row):
        return report_issue_allowed(row, fresh_batches(store, now))
    if row.get('source') == 'Technical Checks':
        observed = row.get('observed_at') or row.get('last_seen')
        # A report-generation date is never evidence of a new HTTP check.
        if not fresh_date(observed, now):
            return False
        expected_status='failed' if row.get('kind')=='check_failed' else 'success'
        return any(r.get('url') == row.get('url') and r.get('check_status') == expected_status
                   and r.get('checked_at') == observed for r in store.read('Technical Checks'))
    return True

def retire_stale(rows, store, now=None):
    sources = store.read('Sitemap Sources')
    complete = bool(sources) and all(r.get('status') == 'success' and fresh_date(r.get('checked_at'), now) for r in sources)
    candidates = {r.get('url') for r in store.read('Sitemap URLs')}
    # Read the user-owned register without invoking registry(), which writes checks.
    candidates.update(str(r.get('Urls', '')).strip() for r in store.read('Page name - manual management'))
    batches = fresh_batches(store, now)
    ids = {r['id'] for r in batches}
    candidates.update(r.get('url') for r in store.read('SF Pages') if r.get('batch') in ids)
    for row in rows:
        if row.get('state') == 'resolved':
            continue
        if is_sf_issue(row) and not report_issue_allowed(row, batches):
            row['state'] = 'historical'
            row['priority_reason'] = '历史抓取证据；非当前确认故障，未宣称已修复'
        elif row.get('source') == 'Technical Checks' and not fresh_date(row.get('observed_at') or row.get('last_seen'), now):
            row['state'] = 'historical' if complete and row.get('url') not in candidates else 'needs_recheck'
            row['priority_reason'] = '历史证据，当前未复核；不得当作今日确认的 P1/P2 故障'
    return rows
