"""48-hour Clarity snapshots, with a bounded GSC-selected page watchlist."""
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo
import requests
from .core import LAUNCH, digest, language, stamp
from .clarity_summary import CORE, flatten
from .storage import ApiFailure

ANCHOR = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
INTERVAL = timedelta(hours=48)
ENDPOINT = 'https://www.clarity.ms/export-data/api/v1/project-live-insights'


def slot_start(now):
    """Fixed slots tolerate runner jitter and do not reset at month boundaries."""
    if now < ANCHOR:
        return None
    return ANCHOR + ((now - ANCHOR) // INTERVAL) * INTERVAL


def page_key(url):
    p = urlsplit(str(url))
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', '', ''))


def select_pages(api, now):
    end = now.astimezone(ZoneInfo('America/Los_Angeles')).date() - timedelta(days=1)
    start = max(LAUNCH, end - timedelta(days=14))
    _, meta, _ = api.gsc(start, end, ['date'], state='all')
    boundary = meta.get('firstIncompleteDate') or meta.get('first_incomplete_date')
    if boundary:
        end = min(end, date.fromisoformat(boundary) - timedelta(days=1))
    else:
        dates, _, _ = api.gsc(start, end, ['date'], state='final')
        if not dates:
            return [], {'status': 'waiting_for_final_gsc'}
        end = date.fromisoformat(max(r['date'] for r in dates))
    if end < LAUNCH:
        return [], {'status': 'waiting_for_final_gsc'}
    start = max(LAUNCH, end - timedelta(days=6))
    rows, _, _ = api.gsc(start, end, ['page'], state='final', prefix='/', limit=20)
    # GSC returns pages ordered by clicks. Never sum users/rates across URL variants.
    selected = []
    seen = set()
    for r in sorted(rows, key=lambda r: (-float(r['clicks']), r['page'])):
        url = page_key(r['page'])
        if float(r['clicks']) <= 0 or language(url) is None or url in seen:
            continue
        seen.add(url)
        selected.append({'page_url': url, 'language': language(url), 'gsc_rank': len(selected)+1,
                         'gsc_clicks': r['clicks'], 'gsc_start': str(start), 'gsc_end': str(end)})
    return selected[:20], {'status': 'selected' if selected else 'no_clicked_pages',
                          'gsc_start': str(start), 'gsc_end': str(end)}


def page_rows(payload, selected, context):
    wanted = {r['page_url'] for r in selected}
    metrics = {url: {} for url in wanted}
    ambiguous = {url: set() for url in wanted}
    possible_cap = False
    for item in payload:
        name = item.get('metricName')
        if name not in CORE:
            continue
        info = item.get('information', [])
        possible_cap |= len(info) >= 1000
        for row in info:
            url = page_key(row.get('Url') or row.get('URL') or row.get('url') or '')
            if url not in wanted:
                continue
            if name in metrics[url] or name in ambiguous[url]:
                metrics[url].pop(name, None)
                ambiguous[url].add(name)
            else:
                metrics[url][name] = row
    result = []
    for target in selected:
        url = target['page_url']
        row = flatten(metrics[url], {**context, **target, 'id': digest([context['snapshot_id'], url]),
                                    'scope': 'Clarity returned URL rows; all traffic channels'})
        row.update(ambiguous_metrics=sorted(ambiguous[url]), possible_api_row_cap=possible_cap,
                   data_status='ambiguous_url_variants' if ambiguous[url] else
                   'not_returned' if not metrics[url] else 'partial' if row['missing_metrics'] else 'returned')
        result.append(row)
    return result


def collect(store, token, now, api=None):
    slot = slot_start(now)
    if slot is None:
        return {'status': 'scheduled_48h', 'next_due': ANCHOR.isoformat()}
    if not token:
        return {'status': 'not_configured', 'detail': 'CLARITY_API_TOKEN missing'}
    snapshot_id = digest(['clarity-48h-v1', slot.isoformat()])
    day = now.astimezone(timezone.utc).date().isoformat()
    context = {'snapshot_id': snapshot_id, 'day': day, 'cadence': 'every_48h',
               'slot_start': slot.isoformat(), 'window_start': (now-timedelta(hours=72)).isoformat(),
               'window_end': now.isoformat(), 'window_type': 'rolling_72h', 'timezone': 'UTC',
               'collected_at': stamp()}
    session = requests.Session()
    session.headers['Authorization'] = 'Bearer ' + token
    results = {}

    def previous(view):
        return [r for r in store.read('Clarity Requests')
                if r.get('snapshot_id') == snapshot_id and r.get('view') == view]

    def done(view):
        return any(r.get('status') in ('success', 'partial', 'no_clicked_pages') for r in previous(view))

    def fetch(view, params, save):
        prior = previous(view)
        if len(prior) >= 3:
            return {'status': 'retry_limit'}
        if sum(r.get('day') == day for r in store.read('Clarity Requests')) >= 10:
            return {'status': 'daily_quota_limit'}
        record = {'id': digest([snapshot_id, view, len(prior)+1]), 'snapshot_id': snapshot_id,
                  'day': day, 'view': view, 'cadence': 'every_48h', 'num_of_days': 3,
                  'attempts': len(prior)+1, 'at': stamp(), 'status': 'attempting'}
        # Persist attempts before HTTP, including timeouts/process interruption.
        store.upsert('Clarity Requests', [record]); store.flush()
        try:
            requested_at = datetime.now(timezone.utc)
            response = session.get(ENDPOINT, params=params, timeout=60)
            record['http_status'] = response.status_code
            if response.status_code != 200:
                raise ApiFailure(f'Clarity HTTP {response.status_code}')
            payload = response.json()
            if not isinstance(payload, list):
                raise ApiFailure('Unexpected Clarity response shape')
            result = save(payload, {**context, 'window_start': (requested_at-timedelta(hours=72)).isoformat(),
                                    'window_end': requested_at.isoformat(), 'collected_at': stamp()})
            store.flush()
            store.upsert('Clarity Requests', [{**record, **result}]); store.flush()
            return result
        except Exception as exc:
            store.upsert('Clarity Requests', [{**record, 'status': 'failed', 'error_type': type(exc).__name__}])
            store.flush()
            return {'status': 'failed', 'error_type': type(exc).__name__}

    def save_overall(payload, request_context):
        metrics = {i['metricName']: i['information'][0] for i in payload
                   if i.get('metricName') in CORE and len(i.get('information', [])) == 1}
        row = flatten(metrics, {**request_context, 'id': snapshot_id, 'coverage': 'project_aggregate'})
        store.upsert('Clarity Snapshots', [row])
        return {'status': 'partial' if row['missing_metrics'] else 'success', 'rows': 1}

    results['overall'] = {'status': 'cached'} if done('overall') else fetch('overall', {'numOfDays': 3}, save_overall)
    if done('URL'):
        results['pages'] = {'status': 'cached'}
    elif api is None:
        results['pages'] = {'status': 'waiting_for_gsc_api'}
    else:
        try:
            selected, selection = select_pages(api, now)
            if not selected:
                results['pages'] = selection
            else:
                def save_pages(payload, request_context):
                    rows = page_rows(payload, selected, request_context)
                    store.upsert('Clarity Pages', rows)
                    return {**selection, 'status': 'success', 'rows': len(rows),
                            'not_returned': sum(r['data_status'] == 'not_returned' for r in rows)}
                results['pages'] = fetch('URL', {'numOfDays': 3, 'dimension1': 'URL'}, save_pages)
        except Exception as exc:
            results['pages'] = {'status': 'failed', 'error_type': type(exc).__name__}
    states = {r['status'] for r in results.values()}
    status = 'cached' if states == {'cached'} else 'success' if states <= {'cached', 'success', 'no_clicked_pages'} else 'partial'
    return {'status': status, **results, 'next_due': (slot+INTERVAL).isoformat(), 'window_type': 'rolling_72h'}
