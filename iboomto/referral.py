"""Top 30 GA4 Referral session sources per property and calendar period."""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import DATA_ID, LAUNCH, daily_window, days, digest, parse_properties, stamp

TAB = 'GA4 Referral'
METRICS = ['sessions', 'activeUsers', 'totalUsers', 'newUsers', 'engagedSessions',
           'engagementRate', 'averageSessionDuration', 'eventCount', 'keyEvents']
TOP = 30
VERSION = 'referral-top30-v1'


def collect_referral(api, store, prop, start, end, now, period='daily'):
    from .analytics import ga_filter, ga_quality
    from .collectors import append_filter, save, scope
    if period not in ('daily', 'weekly', 'monthly'):
        raise ValueError('Referral periods are daily, weekly, or monthly.')
    if start > end:
        raise ValueError('Start must not exceed end.')
    if end < LAUNCH:
        return {'status': 'prelaunch', 'rows': 0, 'requests': 0}
    tz = api.ga_timezone(prop['id'])
    if end >= now.astimezone(ZoneInfo(tz)).date():
        raise ValueError('Referral collection requires completed dates in the GA4 property timezone.')
    qstart = max(start, LAUNCH)
    scoped = scope('', '', True)
    ranges = [(d, d) for d in days(qstart, end)] if period == 'daily' else [(start, end)]
    total = 0
    for rs, re in ranges:
        filters = append_filter(ga_filter(), 'sessionDefaultChannelGroup', ['Referral'])
        rows, meta = api.ga(prop['id'], max(rs, LAUNCH), re, ['sessionSource'], METRICS,
                            filters, limit=TOP, order='sessions')
        # The API orders and limits before returning. This also makes test/local
        # adapters deterministic and never expands a top-30 selection.
        rows = sorted(rows, key=lambda r: (-float(r['sessions']), str(r['sessionSource'])))[:TOP]
        base = {'source': 'GA4', 'property': prop['id'], 'language': prop['language'],
                'period': period, 'start': str(rs), 'end': str(re), 'timezone': tz,
                'channel': 'Referral', 'channel_scope': 'Session default channel group',
                'quality': ga_quality(meta, re, tz, now, rs), 'collected_at': stamp(),
                'scope': scoped, 'scope_version': VERSION, 'metadata': meta,
                'hostname_filter': 'hostName EXACT www.iboomto.com',
                'selection_reason': 'top30_sessions_within_referral', 'run_id': os.environ.get('GITHUB_RUN_ID', '')}
        packed = []
        for rank, raw in enumerate(rows, 1):
            source = str(raw['sessionSource'])
            record = {**base, 'session_source': source, 'rank': rank, 'data_status': 'returned',
                      **{key: raw[key] for key in METRICS if key in raw},
                      'dimensions': json.dumps({'sessionSource': source}, sort_keys=True),
                      'key_events_per_user': raw.get('keyEvents', 0) / raw['totalUsers'] if raw.get('totalUsers') else ''}
            record['id'] = digest([TAB, prop['id'], period, str(rs), str(re), source, scoped])
            packed.append(record)
        if not packed:
            # A coverage record, not a fictitious source or invented zero metrics.
            packed = [{**base, 'id': digest([TAB, prop['id'], period, str(rs), str(re), '', scoped]),
                       'session_source': '', 'rank': '', 'data_status': 'no_data_returned',
                       **dict.fromkeys(METRICS, '')}]

        def partition(row):
            return (str(row.get('property')) == str(prop['id']) and row.get('period') == period and
                    row.get('start') == str(rs) and row.get('end') == str(re) and row.get('scope') == scoped)

        save(store, TAB, packed, partition, METRICS)
        total += len(packed)
    return {'status': ga_quality({}, end, tz, now, start), 'rows': total, 'requests': len(ranges)}


def backfill_ranges(end):
    """Match existing Sunday–Saturday weeks and calendar months, including launch partials."""
    ranges = [('daily', LAUNCH, end)] if end >= LAUNCH else []
    cursor = LAUNCH - timedelta(days=(LAUNCH.weekday() + 1) % 7)
    while cursor + timedelta(days=6) <= end:
        ranges.append(('weekly', cursor, cursor + timedelta(days=6)))
        cursor += timedelta(days=7)
    cursor = LAUNCH.replace(day=1)
    while True:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = next_month - timedelta(days=1)
        if last > end:
            break
        ranges.append(('monthly', cursor, last))
        cursor = next_month
    return ranges


def main():
    """One-time/repeatable backfill; daily collection is integrated into the monitor."""
    from .analytics import Analytics
    from .api_usage import METER
    from .storage import ApiFailure, Sheets, google_session
    now = datetime.now(timezone.utc)
    run_id = os.environ.get('GITHUB_RUN_ID') or digest(stamp())
    METER.reset(run_id)
    store = Sheets(google_session(), os.environ.get('IBOOMTO_SHEET_ID') or DATA_ID, True)
    api = Analytics(google_session())
    statuses = []
    started = stamp()
    failure = False
    output = Path('runtime/ga4-referral-backfill.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for prop in parse_properties(store.read('Properties')):
            end = daily_window(now, api.ga_timezone(prop['id']))[1]
            for period, rs, re in backfill_ranges(end):
                began = stamp()
                try:
                    result = collect_referral(api, store, prop, rs, re, now, period)
                    status = 'success'
                except Exception as exc:
                    failure = True
                    result = {'error_type': type(exc).__name__, 'message': str(exc) if isinstance(exc, (ValueError, ApiFailure)) else 'API collection failed; completed partitions are preserved.'}
                    status = 'failed'
                row = {'id': digest([run_id, 'GA4 Referral backfill', prop['id'], period, str(rs), str(re)]),
                       'source': 'GA4 Referral backfill ' + prop['language'], 'run_id': run_id,
                       'status': status, 'started_at': began, 'finished_at': stamp(),
                       'detail': {'period': period, 'start': str(rs), 'end': str(re), **result}}
                statuses.append(row)
                store.upsert('Run Status', [row])
                store.flush()
                print(json.dumps(row), flush=True)
                output.write_text(json.dumps({'run_id': run_id, 'statuses': statuses}, indent=2), encoding='utf-8')
    finally:
        store.upsert('API Usage', METER.rows())
        store.flush()
        rows = store.read(TAB)
        report = {'run_id': run_id, 'started_at': started, 'finished_at': stamp(), 'statuses': statuses,
                  'rows': len(rows), 'languages': sorted({r['language'] for r in rows}),
                  'counts': {p: sum(r['period'] == p for r in rows) for p in ('daily', 'weekly', 'monthly')},
                  'workbook_url': store.link(TAB), 'api_usage': METER.rows()}
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
                handle.write('## GA4 Referral backfill\n\n[Open GA4 Referral](' + store.link(TAB) + ')\n\n')
                handle.write('Top 30 session sources by sessions, filtered to Session default channel group = Referral.\n\n')
                handle.write('Rows by period: ' + json.dumps(report['counts']) + '\n\n')
                handle.write('Languages: ' + ', '.join(report['languages']) + '\n\n')
                handle.write('Failed partitions: ' + str(sum(s['status'] == 'failed' for s in statuses)) + '\n')
    return 1 if failure else 0


if __name__ == '__main__':
    sys.exit(main())
