"""Crawl timestamps and eligibility for routine SF evidence."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


JST = ZoneInfo('Asia/Tokyo')
SF_POLICY = 'latest-verified-v2'
VERIFIED_POLICIES = {'same-jst-day-v1', SF_POLICY}


def crawl_time(value):
    value = str(value or '').strip()
    try:
        if len(value) == 8 and value.isdigit():
            return datetime.strptime(value, '%Y%m%d').replace(tzinfo=JST)
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.astimezone(JST) if dt.tzinfo else dt.replace(tzinfo=JST)
    except ValueError:
        return None


def crawl_day(value):
    dt = crawl_time(value)
    return dt.date() if dt else None


def fresh_date(value, now=None):
    now = now or datetime.now(timezone.utc)
    return crawl_day(value) == now.astimezone(JST).date()


def latest_batch(rows):
    successful = [r for r in rows if r.get('status') == 'success']
    def key(row):
        observed = crawl_time(row.get('crawl_timestamp')) or crawl_time(row.get('batch_date'))
        return (observed or datetime.min.replace(tzinfo=JST), str(row.get('checked_at') or ''),
                row.get('freshness_policy') in VERIFIED_POLICIES)
    return max(successful, key=key, default=None)


def fresh_batches(store, now=None):
    latest = latest_batch(store.read('Import Batches'))
    if latest and latest.get('freshness_policy') in VERIFIED_POLICIES:
        observed = crawl_day(latest.get('crawl_timestamp'))
        today = (now or datetime.now(timezone.utc)).astimezone(JST).date()
        if observed and 0 <= (today - observed).days <= 1:
            return [latest]
    return []


def is_sf_issue(row):
    return (str(row.get('source', '')).startswith(('SF ', 'Screaming Frog'))
            or str(row.get('kind', '')).startswith('sf_')
            or row.get('kind') == 'no_internal_inlink_in_export')


def issue_batch(row):
    detail = row.get('evidence') or {}
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except ValueError:
            detail = {}
    return row.get('sf_batch') or (detail.get('batch') if isinstance(detail, dict) else None)


def report_issue_allowed(row, batches):
    return not is_sf_issue(row) or issue_batch(row) in {r['id'] for r in batches}
