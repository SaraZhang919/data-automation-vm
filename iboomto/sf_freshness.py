"""Routine SF evidence is limited to a verified crawl from today's JST date."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def crawl_day(value):
    value = str(value or '').strip()
    try:
        if len(value) == 8 and value.isdigit():
            return datetime.strptime(value, '%Y%m%d').date()
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (dt.astimezone(ZoneInfo('Asia/Tokyo')) if dt.tzinfo else dt).date()
    except ValueError:
        return None


def fresh_date(value, now=None):
    now = now or datetime.now(timezone.utc)
    return crawl_day(value) == now.astimezone(ZoneInfo('Asia/Tokyo')).date()


def fresh_batches(store, now=None):
    return [r for r in store.read('Import Batches') if r.get('status') == 'success'
            and r.get('freshness_policy') == 'same-jst-day-v1'
            and fresh_date(r.get('crawl_timestamp'), now)]


def is_sf_issue(row):
    return (str(row.get('source', '')).startswith(('SF ', 'Screaming Frog'))
            or str(row.get('kind', '')).startswith('sf_')
            or row.get('kind') == 'no_internal_inlink_in_export')


def report_issue_allowed(row, batches):
    if not is_sf_issue(row):
        return True
    detail = row.get('evidence') or {}
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except ValueError:
            detail = {}
    batch = row.get('sf_batch') or (detail.get('batch') if isinstance(detail, dict) else None)
    return batch in {r['id'] for r in batches}
