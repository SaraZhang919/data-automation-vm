"""On-demand event totals and independent landing/event-page breakdowns."""
import argparse
import json
import os
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
HEADERS = ['event_name', 'eventCount', 'start', 'end', 'language', 'activeUsers',
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
        terms = [part.strip() for part in value.split('|') if part.strip()]
        if not terms or any(term.lower() == 'all' for term in terms):
            raise ValueError('Use all alone, or provide event names separated by |.')
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

    def filters(self):
        from .analytics import ga_filter
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
        return filters


def headers(tab):
    result = list(HEADERS)
    if VIEWS[tab]:
        result.insert(8, PAGE_FIELDS[VIEWS[tab]])
    return result


def worst_quality(values):
    order = {'mature': 0, 'prelaunch': 1, 'partial_launch': 2, 'provisional': 3, 'limited': 4}
    return max(values, key=lambda value: order[value], default='mature')


def fetch_property(api, prop, start, end, now, selection, run_id):
    """Stage all views before changing any stored partition."""
    from .analytics import ga_quality
    if start > end:
        raise ValueError('Start must not exceed end.')
    tz = api.ga_timezone(prop['id'])
    if end > now.astimezone(ZoneInfo(tz)).date():
        raise ValueError('End date must not be in the future in the GA4 property timezone.')
    base = {'start': str(start), 'end': str(end), 'language': prop['language'],
            'property': prop['id'], 'timezone': tz, 'collected_at': stamp(),
            'run_id': run_id, 'event_match': selection.match, 'event_filter': selection.label,
            'hostname_filter': 'hostName EXACT www.iboomto.com', 'scope_version': VERSION,
            'aggregation_note': ''}
    staged = {}
    for tab, dimension in VIEWS.items():
        dimensions = ['eventName'] + ([dimension] if dimension else [])
        rows, metadata = (api.ga(prop['id'], max(start, LAUNCH), end, dimensions,
                                 METRICS, selection.filters()) if end >= LAUNCH else ([], {}))
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
            record['id'] = digest([VERSION, tab, prop['id'], str(start), str(end), event, page])
            packed.append(record)
        if not packed:
            packed = [{**base, 'event_name': '', 'data_status': 'prelaunch' if end < LAUNCH else 'no_data_returned',
                       'quality': quality, 'metadata': metadata, **dict.fromkeys(METRICS, ''),
                       'id': digest([VERSION, tab, prop['id'], str(start), str(end), 'coverage',
                                     selection.match, selection.terms])}]
        staged[tab] = packed
    return staged


def partition(row, language, start, end, selection):
    if (row.get('language') != language or row.get('start') != str(start) or
            row.get('end') != str(end) or row.get('scope_version') != VERSION):
        return False
    if row.get('event_name'):
        return selection.matches(row['event_name'])
    return (not selection.terms or
            (row.get('event_match') == selection.match and row.get('event_filter') == selection.label))


def replace_results(store, staged, language, start, end, selection):
    for tab, records in staged.items():
        old = [row for row in store.read(tab) if not partition(row, language, start, end, selection)]
        indexed = {row['id']: row for row in old}
        indexed.update({row['id']: row for row in records})
        ordered = sorted(indexed.values(), key=lambda row: (
            row.get('start', ''), row.get('end', ''), row.get('event_name', ''),
            row.get('language') != 'all', row.get('language', ''),
            row.get('landing_page', ''), row.get('event_page', ''), row['id']))
        store.set(tab, ordered, headers(tab))


def aggregate(results, start, end, selection, run_id):
    """Use only summary rows fetched in this run, never page rows or cached totals."""
    rows = [row for staged in results for row in staged[SUMMARY]]
    if {row['language'] for row in rows} != set(LANGS):
        raise ValueError('All-language totals require all nine language queries to succeed.')
    timezones = {row['timezone'] for row in rows}
    base = {'start': str(start), 'end': str(end), 'language': 'all', 'property': 'all',
            'timezone': next(iter(timezones)) if len(timezones) == 1 else 'mixed (property local dates)',
            'collected_at': stamp(), 'run_id': run_id, 'event_match': selection.match,
            'event_filter': selection.label, 'hostname_filter': 'hostName EXACT www.iboomto.com',
            'scope_version': VERSION, 'aggregation_note': TOTAL_NOTE,
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
                       'id': digest([VERSION, SUMMARY, 'all', str(start), str(end), event, ''])})
    if not packed:
        packed = [{**base, 'event_name': '', 'data_status': 'prelaunch' if end < LAUNCH else 'no_data_returned',
                   **dict.fromkeys(METRICS, ''),
                   'id': digest([VERSION, SUMMARY, 'all', str(start), str(end), 'coverage', selection.match, selection.terms])}]
    return {SUMMARY: packed}


def mark_failed_total(store, start, end, selection, run_id, failed_languages):
    prior = [row for row in store.read(SUMMARY) if partition(row, 'all', start, end, selection)]
    failure = {'last_attempt_at': stamp(), 'last_attempt_run_id': run_id,
               'refresh_error': 'Failed languages: ' + ', '.join(sorted(failed_languages)),
               'data_status': 'refresh_failed'}
    if not prior:
        prior = [{'id': digest([VERSION, SUMMARY, 'all', str(start), str(end), 'coverage', selection.match, selection.terms]),
                  'start': str(start), 'end': str(end), 'language': 'all', 'property': 'all',
                  'event_name': '', 'event_match': selection.match, 'event_filter': selection.label,
                  'scope_version': VERSION, 'aggregation_note': TOTAL_NOTE, **dict.fromkeys(METRICS, '')}]
    replace_results(store, {SUMMARY: [{**row, **failure} for row in prior]}, 'all', start, end, selection)


def run_check(api, store, props, start, end, selection, now, run_id, language='all'):
    from .storage import ApiFailure
    if start > end:
        raise ValueError('Start must not exceed end.')
    if language not in ('all', *LANGS):
        raise ValueError('Unsupported language.')
    if {prop['language'] for prop in props} != set(LANGS) or len(props) != len(LANGS):
        raise ValueError('Expected exactly nine configured language properties.')
    results, statuses, failed = [], [], []
    for prop in props:
        if language not in ('all', prop['language']):
            continue
        began = stamp()
        try:
            staged = fetch_property(api, prop, start, end, now, selection, run_id)
            replace_results(store, staged, prop['language'], start, end, selection)
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
                             'event_match': selection.match, **detail}}
        statuses.append(record)
        store.upsert('Run Status', [record])
        print(json.dumps({'language': prop['language'], 'status': status}), flush=True)
    if language == 'all':
        if failed:
            mark_failed_total(store, start, end, selection, run_id, failed)
        else:
            replace_results(store, aggregate(results, start, end, selection, run_id), 'all', start, end, selection)
    return {'status': 'failed' if failed else 'success', 'failed_languages': failed,
            'start': str(start), 'end': str(end), 'language': language,
            'event_filter': selection.label, 'event_match': selection.match,
            'run_id': run_id, 'statuses': statuses,
            'rows': {tab: sum(1 for row in store.read(tab) if row.get('start') == str(start) and row.get('end') == str(end)) for tab in VIEWS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default=os.environ.get('INPUT_START'))
    parser.add_argument('--end', default=os.environ.get('INPUT_END'))
    parser.add_argument('--language', choices=['all', *LANGS], default=os.environ.get('INPUT_LANGUAGE') or 'all')
    parser.add_argument('--event-names', default=os.environ.get('INPUT_EVENT_NAMES', ''))
    parser.add_argument('--event-match', choices=['exact', 'contains'], default=os.environ.get('INPUT_EVENT_MATCH') or 'exact')
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
    from .storage import Sheets, google_session
    run_id = os.environ.get('GITHUB_RUN_ID') or digest(stamp())
    METER.reset(run_id)
    session = google_session()
    store = Sheets(session, os.environ.get('IBOOMTO_SHEET_ID') or DATA_ID, args.write)
    report = run_check(Analytics(session), store, parse_properties(store.read('Properties')),
                       start, end, selection, datetime.now(timezone.utc), run_id, args.language)
    store.upsert('API Usage', METER.rows())
    store.flush()
    report['links'] = {tab: store.link(tab) for tab in VIEWS}
    report['api_usage'] = METER.rows()
    report['writes_enabled'] = args.write
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
            handle.write('## Event Check — iBoomto\n\n')
            handle.write(f"{start} to {end}; language: {args.language}; status: {report['status']}.\n\n")
            for tab, link in report['links'].items():
                handle.write(f'- [{tab}]({link})\n')
            handle.write('\n' + TOTAL_NOTE + '\n')
            if report['failed_languages']:
                handle.write('\nFailed languages: ' + ', '.join(report['failed_languages']) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'rows', 'links')}), flush=True)
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    sys.exit(main())
