"""Choose a separate URL Inspection rotation for each language site."""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .core import LANGS, language


def needs_index_review(url, row):
    """Prioritize actionable non-indexing evidence, not every non-PASS verdict."""
    raw = row.get('result') or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = {}
    state = raw.get('indexStatusResult', {}) if isinstance(raw, dict) else {}
    coverage = str(row.get('coverage_state') or state.get('coverageState') or '').lower()
    verdict = row.get('verdict') or state.get('verdict')
    if verdict == 'PASS':
        return False
    if any(word in coverage for word in ('noindex', 'redirect', 'canonical', 'duplicate', 'robots', 'not found', '404', 'soft 404')):
        return False
    if state.get('indexingState', '').startswith('BLOCKED_') or state.get('robotsTxtState') == 'DISALLOWED':
        return False
    for key, raw_key in (('google_canonical', 'googleCanonical'), ('user_canonical', 'userCanonical')):
        canonical = row.get(key) or state.get(raw_key)
        if canonical and canonical != url:
            return False
    return 'not indexed' in coverage or (
        verdict in ('FAIL', 'NEUTRAL') and state.get('indexingState') == 'INDEXING_ALLOWED'
        and (row.get('page_fetch_state') or state.get('pageFetchState')) == 'SUCCESSFUL')


def checked_time(row):
    try:
        dt = datetime.fromisoformat(str(row.get('checked_at', '')).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except ValueError:
        return None


def select_inspection_urls(candidates, previous, priority, per_language=30, now=None):
    # Reserve thirds for discovery, due follow-ups, and regular rotation.
    # Spare slots can move between groups, but never between languages.
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    limit = min(100, max(1, int(per_language)))
    buckets = {lg: [] for lg in LANGS}
    for url in set(candidates) | set(priority):
        lg = language(url)
        if lg in buckets:
            buckets[lg].append(url)
    selected = []
    for lg in LANGS:
        groups = [[], [], []]
        for url in buckets[lg]:
            if url not in previous:
                groups[0].append(url)
                continue
            row = previous[url]
            last = checked_time(row)
            failed = row.get('api_status') == 'failed'
            unindexed = needs_index_review(url, row)
            if failed:
                if last and last.astimezone(ZoneInfo('Asia/Tokyo')).date() >= now.astimezone(ZoneInfo('Asia/Tokyo')).date():
                    continue
            elif unindexed and last and now - last < timedelta(days=3):
                continue
            groups[1 if failed or unindexed else 2].append(url)
        def oldest(u):
            return (checked_time(previous.get(u, {})) or datetime.min.replace(tzinfo=timezone.utc), u not in priority, u)
        groups[0].sort(key=lambda u: (u not in priority, u))
        groups[1].sort(key=oldest)
        groups[2].sort(key=oldest)
        quota = limit // 3
        quotas = (quota, quota, limit - 2 * quota)
        chosen = [u for group, count in zip(groups, quotas) for u in group[:count]]
        for group in groups:
            for u in group:
                if len(chosen) >= limit:
                    break
                if u not in chosen:
                    chosen.append(u)
        selected.extend(chosen)
    return selected
