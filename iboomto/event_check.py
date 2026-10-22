"""On-demand event totals and independent landing/event-page breakdowns."""
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import DATA_ID, LANGS, LAUNCH, digest, load_local_env, parse_properties, stamp

VERSION = 'event-check-v1'
SUMMARY = 'Event Check Summary'
VIEWS = {SUMMARY: None, 'Event Check Landing Pages': 'landingPage',
         'Event Check Event Pages': 'pageLocation'}
PAGE_FIELDS = {'landingPage': 'landing_page', 'pageLocation': 'event_page'}
METRICS = ['eventCount', 'activeUsers', 'sessions', 'eventsPerSession']
CHANNELS = ('all', 'Organic Search', 'Direct', 'Referral', 'Organic Social',
            'Paid Search', 'Paid Social', 'Email', 'AI Assistant', 'Unassigned',
            'Cross-network', 'Display', 'Affiliates', 'Organic Shopping', 'Organic Video',
            'Paid Shopping', 'Paid Video', 'Paid Other', 'Audio', 'SMS',
            'Mobile Push Notifications', '(not set)')
HEADERS = ['event_name', 'eventCount', 'start', 'end', 'language', 'channel', 'activeUsers',
           'sessions', 'eventsPerSession', 'data_status', 'quality', 'timezone',
           'aggregation_note', 'collected_at', 'run_id', 'event_match', 'event_filter',
           'property', 'hostname_filter', 'scope_version', 'id', 'metadata']
TOTAL_NOTE = ('Active users and sessions are summed across language properties, '
              'not deduplicated across properties. Events per session = summed '
              'event count / summed sessions. Dates use each property timezone.')


@dataclass(frozen=True)
class Selection:
    terms: tuple = ()
    match: str = 'exact'

    @classmethod
    def parse(cls, value='', match='exact'):
        if match not in ('exact', 'contains'):
            raise ValueError('Event match must be exact or contains.')
        if not value.strip() or value.strip().lower() == 'all':
            return cls((), match)
        terms = [part for part in re.split(r'[|,\s]+', value.strip()) if part]
        if not terms or any(term.lower() == 'all' for term in terms):
            raise ValueError('Use all alone, or separate event names with |, commas, or spaces.')
        if match == 'contains':
            terms = [term.lower() for term in terms]
        return cls(tuple(sorted(set(terms))), match)

    @property
    def label(self):
        return '|'.join(self.terms) or 'all'

    def matches(self, name):
        if not self.terms:
            return True
        if self.match == 'exact':
            return name in self.terms
        return any(term in name.lower() for term in self.terms)

    def filters(self, channel='all'):
        from .analytics import ga_filter
        if channel not in CHANNELS:
            raise ValueError('Unsupported session default channel group.')
        filters = ga_filter()
        if self.terms:
            if self.match == 'exact':
                event = {'filter': {'fieldName': 'eventName', 'inListFilter': {
                    'values': list(self.terms), 'caseSensitive': True}}}
            else:
                event = {'orGroup': {'expressions': [
                    {'filter': {'fieldName': 'eventName', 'stringFilter': {
                        'matchType': 'CONTAINS', 'value': term, 'caseSensitive': False}}}
                    for term in self.terms]}}
            filters['andGroup']['expressions'].append(event)
        if channel != 'all':
            filters['andGroup']['expressions'].append({'filter': {
                'fieldName': 'sessionDefaultChannelGroup', 'stringFilter': {
                    'matchType': 'EXACT', 'value': channel, 'caseSensitive': True}}})
        return filters


def scoped_id(parts, channel):
    # Keep the IDs of historical, unfiltered reports unchanged.
    return digest(parts + (['session_channel', channel] if channel != 'all' else []))


def headers(tab):
    result = list(HEADERS)
    if VIEWS[tab]:
        result.insert(result.index('eventsPerSession')+1, PAGE_FIELDS[VIEWS[tab]])
    return result


def worst_quality(values):
    order = {'mature': 0, 'prelaunch': 1, 'partial_launch': 2, 'provisional': 3, 'limited': 4}
    return max(values, key=lambda value: order[value], default='mature')


def fetch_property(api, prop, start, end, now, selection, run_id, channel='all'):
    """Stage all views before changing any stored partition."""
    from .analytics import ga_quality
    if start > end:
        raise ValueError('Start must not exceed end.')
    filters = selection.filters(channel)
    tz = api.ga_timezone(prop['id'])
    if end > now.astimezone(ZoneInfo(tz)).date():
        raise ValueError('End date must not be in the future in the GA4 property timezone.')
    base = {'start': str(start), 'end': str(end), 'language': prop['language'],
            'property': prop['id'], 'timezone': tz, 'collected_at': stamp(),
            'run_id': run_id, 'event_match': selection.match, 'event_filter': selection.label,
            'hostname_filter': 'hostName EXACT www.iboomto.com', 'scope_version': VERSION,
            'aggregation_note': '', 'channel': channel}
    staged = {}
    for tab, dimension in VIEWS.items():
        dimensions = ['eventName'] + ([dimension] if dimension else [])
        rows, metadata = (api.ga(prop['id'], max(start, LAUNCH), end, dimensions,
                                 METRICS, filters) if end >= LAUNCH else ([], {}))
        quality = ga_quality(metadata, end, tz, now, start) if end >= LAUNCH else 'prelaunch'
        packed = []
        for raw in rows:
            event = raw['eventName']
            if not selection.matches(event):
                raise ValueError('GA4 returned an event outside the requested filter.')
            record = {**base, 'event_name': event, 'data_status': 'returned',
                      'quality': quality, 'metadata': metadata,
                      **{key: raw[key] for key in METRICS}}
            page = raw.get(dimension, '') if dimension else ''
            if dimension:
                record[PAGE_FIELDS[dimension]] = page
            record['id'] = scoped_id([VERSION, tab, prop['id'], str(start), str(end), event, page], channel)
            packed.append(record)
        if not packed:
            packed = [{**base, 'event_name': '', 'data_status': 'prelaunch' if end < LAUNCH else 'no_data_returned',
                       'quality': quality, 'metadata': metadata, **dict.fromkeys(METRICS, ''),
                       'id': scoped_id([VERSION, tab, prop['id'], str(start), str(end), 'coverage',
                                        selection.match, selection.terms], channel)}]
        staged[tab] = packed
    return staged


def partition(row, language, start, end, selection, channel='all'):
    if (row.get('language') != language or row.get('start') != str(start) or
            row.get('end') != str(end) or row.get('scope_version') != VERSION or
            (row.get('channel') or 'all') != channel):
        return False
    if row.get('event_name'):
        return selection.matches(row['event_name'])
    if not selection.terms:
        return True
    if row.get('event_match') != selection.match:
        return False
    try:
        return Selection.parse(str(row.get('event_filter', '')), selection.match).terms == selection.terms
    except ValueError:
        return False


def replace_results(store, staged, language, start, end, selection, channel='all'):
    for tab, records in staged.items():
        old = [{**row, 'channel': row.get('channel') or 'all'} for row in store.read(tab)
               if not partition(row, language, start, end, selection, channel)]
        indexed = {row['id']: row for row in old}
        indexed.update({row['id']: row for row in records})
        ordered = sorted(indexed.values(), key=lambda row: (
            row.get('start', ''), row.get('end', ''), row.get('event_name', ''),
            row.get('channel', 'all') != 'all', row.get('channel', 'all'),
            row.get('language') != 'all', row.get('language', ''),
            row.get('landing_page', ''), row.get('event_page', ''), row['id']))
        store.set(tab, ordered, headers(tab))


def aggregate(results, start, end, selection, run_id, channel='all'):
    """Use only summary rows fetched in this run, never page rows or cached totals."""
    rows = [row for staged in results for row in staged[SUMMARY]]
    if {row['language'] for row in rows} != set(LANGS):
        raise ValueError('All-language totals require all nine language queries to succeed.')
    if any((row.get('channel') or 'all') != channel for row in rows):
        raise ValueError('All-language totals require the same channel in every language.')
    timezones = {row['timezone'] for row in rows}
    base = {'start': str(start), 'end': str(end), 'language': 'all', 'property': 'all',
            'timezone': next(iter(timezones)) if len(timezones) == 1 else 'mixed (property local dates)',
            'collected_at': stamp(), 'run_id': run_id, 'event_match': selection.match,
            'event_filter': selection.label, 'hostname_filter': 'hostName EXACT www.iboomto.com',
            'scope_version': VERSION, 'aggregation_note': TOTAL_NOTE, 'channel': channel,
            'quality': worst_quality(row['quality'] for row in rows),
            'metadata': {'languages_queried': sorted(LANGS),
                         'source': 'fresh language-level summary queries'}}
    groups = {}
    for row in rows:
        if row['data_status'] == 'returned':
            groups.setdefault(row['event_name'], []).append(row)
    packed = []
    for event, source in sorted(groups.items()):
        counts = {key: sum(float(row[key]) for row in source)
                  for key in ('eventCount', 'activeUsers', 'sessions')}
        packed.append({**base, **counts, 'event_name': event, 'data_status': 'returned',
                       'eventsPerSession': counts['eventCount'] / counts['sessions'] if counts['sessions'] else '',
                       'metadata': {**base['metadata'], 'languages_returning_event': sorted(row['language'] for row in source)},
                       'id': scoped_id([VERSION, SUMMARY, 'all', str(start), str(end), event, ''], channel)})
    if not packed:
        packed = [{**base, 'event_name': '', 'data_status': 'prelaunch' if end < LAUNCH else 'no_data_returned',
                   **dict.fromkeys(METRICS, ''),
                   'id': scoped_id([VERSION, SUMMARY, 'all', str(start), str(end), 'coverage', selection.match, selection.terms], channel)}]
    return {SUMMARY: packed}


def mark_failed_total(store, start, end, selection, run_id, failed_languages, channel='all'):
    prior = [row for row in store.read(SUMMARY) if partition(row, 'all', start, end, selection, channel)]
    failure = {'last_attempt_at': stamp(), 'last_attempt_run_id': run_id,
               'refresh_error': 'Failed languages: ' + ', '.join(sorted(failed_languages)),
               'data_status': 'refresh_failed'}
    if not prior:
        prior = [{'id': scoped_id([VERSION, SUMMARY, 'all', str(start), str(end), 'coverage', selection.match, selection.terms], channel),
                  'start': str(start), 'end': str(end), 'language': 'all', 'property': 'all',
                  'event_name': '', 'event_match': selection.match, 'event_filter': selection.label,
                  'scope_version': VERSION, 'channel': channel, 'aggregation_note': TOTAL_NOTE, **dict.fromkeys(METRICS, '')}]
    replace_results(store, {SUMMARY: [{**row, **failure} for row in prior]}, 'all', start, end, selection, channel)


def run_check(api, store, props, start, end, selection, now, run_id, language='all', channel='all'):
    from .storage import ApiFailure
    if start > end:
        raise ValueError('Start must not exceed end.')
    if language not in ('all', *LANGS):
        raise ValueError('Unsupported language.')
    if channel not in CHANNELS:
        raise ValueError('Unsupported session default channel group.')
    if {prop['language'] for prop in props} != set(LANGS) or len(props) != len(LANGS):
        raise ValueError('Expected exactly nine configured language properties.')
    results, statuses, failed = [], [], []
    for prop in props:
        if language not in ('all', prop['language']):
            continue
        began = stamp()
        try:
            staged = fetch_property(api, prop, start, end, now, selection, run_id, channel)
            replace_results(store, staged, prop['language'], start, end, selection, channel)
            results.append(staged)
            status = 'success'
            detail = {'rows': {tab: len(rows) for tab, rows in staged.items()}}
        except Exception as exc:
            failed.append(prop['language'])
            status = 'failed'
            detail = {'error_type': type(exc).__name__, 'message': str(exc) if isinstance(exc, (ValueError, ApiFailure)) else 'GA4 collection failed; prior results preserved.'}
        record = {'id': digest([run_id, VERSION, prop['id']]), 'source': 'Event Check ' + prop['language'],
                  'status': status, 'run_id': run_id, 'started_at': began, 'finished_at': stamp(),
                  'detail': {'start': str(start), 'end': str(end), 'event_filter': selection.label,
                             'event_match': selection.match, 'channel': channel, **detail}}
        statuses.append(record)
        store.upsert('Run Status', [record])
        print(json.dumps({'language': prop['language'], 'status': status}), flush=True)
    if language == 'all':
        if failed:
            mark_failed_total(store, start, end, selection, run_id, failed, channel)
        else:
            replace_results(store, aggregate(results, start, end, selection, run_id, channel), 'all', start, end, selection, channel)
    return {'status': 'failed' if failed else 'success', 'failed_languages': failed,
            'start': str(start), 'end': str(end), 'language': language, 'channel': channel,
            'event_filter': selection.label, 'event_match': selection.match,
            'run_id': run_id, 'statuses': statuses,
            'rows': {tab: sum(1 for row in store.read(tab) if row.get('start') == str(start) and row.get('end') == str(end) and
                              (row.get('channel') or 'all') == channel) for tab in VIEWS}}


def extend_report_filters(store):
    """Include appended report columns without changing existing filter criteria."""
    from .storage import request
    meta = request(store.s, 'GET', store.base, params={
        'fields': 'sheets(properties(title),basicFilter)'}).json()
    edits = []
    for sheet in meta.get('sheets', []):
        name = sheet['properties']['title']
        basic = sheet.get('basicFilter')
        if name not in VIEWS or not basic:
            continue
        width = len(store.headers[name])
        end = basic['range'].get('endColumnIndex')
        if end is not None and end < width:
            basic = dict(basic)
            if 'filterSpecs' in basic:
                basic.pop('criteria', None)  # Use the current representation, not its deprecated alias.
            edits.append({'setBasicFilter': {'filter': {
                **basic, 'range': {**basic['range'], 'endColumnIndex': width}}}})
    if edits:
        request(store.s, 'POST', store.base+':batchUpdate', json={'requests': edits})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default=os.environ.get('INPUT_START'))
    parser.add_argument('--end', default=os.environ.get('INPUT_END'))
    parser.add_argument('--language', choices=['all', *LANGS], default=os.environ.get('INPUT_LANGUAGE') or 'all')
    parser.add_argument('--event-names', default=os.environ.get('INPUT_EVENT_NAMES', ''))
    parser.add_argument('--event-match', choices=['exact', 'contains'], default=os.environ.get('INPUT_EVENT_MATCH') or 'exact')
    parser.add_argument('--channel', choices=CHANNELS, default=os.environ.get('INPUT_CHANNEL') or 'all')
    parser.add_argument('--env-file')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--output', default='runtime/event-check.json')
    args = parser.parse_args()
    try:
        start, end = date.fromisoformat(args.start or ''), date.fromisoformat(args.end or '')
        selection = Selection.parse(args.event_names, args.event_match)
        if start > end:
            raise ValueError('Start must not exceed end.')
    except ValueError as exc:
        parser.error(str(exc))
    if args.env_file:
        load_local_env(args.env_file)
    from .analytics import Analytics
    from .api_usage import METER
    from .storage import ApiFailure, Sheets, google_session
    run_id = os.environ.get('GITHUB_RUN_ID') or digest(stamp())
    METER.reset(run_id)
    session = google_session()
    store = Sheets(session, os.environ.get('IBOOMTO_SHEET_ID') or DATA_ID, args.write)
    report = run_check(Analytics(session), store, parse_properties(store.read('Properties')),
                       start, end, selection, datetime.now(timezone.utc), run_id, args.language, args.channel)
    report['writes_enabled'] = args.write
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report['write_status'] = 'pending' if args.write else 'dry_run'
    # Keep collection evidence even if a later Sheets write fails.
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    try:
        store.upsert('API Usage', METER.rows())
        store.flush()
        if args.write:
            extend_report_filters(store)
        report['write_status'] = 'success' if args.write else 'dry_run'
    except Exception as exc:
        report['status'] = 'failed'
        report['write_status'] = 'failed'
        report['write_error'] = {'error_type': type(exc).__name__,
                                 'message': str(exc) if isinstance(exc, (ApiFailure, ValueError)) else 'Sheets write failed; see run audit.'}
    finally:
        report['links'] = {tab: store.link(tab) for tab in VIEWS}
        report['api_usage'] = METER.rows()
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
            handle.write('## Event Check — iBoomto\n\n')
            handle.write(f"{start} to {end}; language: {args.language}; session channel: {args.channel}; status: {report['status']}.\n\n")
            for tab, link in report['links'].items():
                handle.write(f'- [{tab}]({link})\n')
            handle.write('\n' + TOTAL_NOTE + '\n')
            if report['failed_languages']:
                handle.write('\nFailed languages: ' + ', '.join(report['failed_languages']) + '\n')
            if report.get('write_error'):
                handle.write('\nSheets write failed: ' + report['write_error']['message'] + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'write_status', 'rows', 'links', 'write_error') if key in report}), flush=True)
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    sys.exit(main())
