import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from iboomto.analytics import Analytics
from iboomto.core import LANGS, LAUNCH, digest
from iboomto.event_check import (CHANNELS, METRICS, SUMMARY, VIEWS, Selection, aggregate,
    extend_report_filters, fetch_property, headers, main, replace_results, run_check)
from iboomto.layout import format_columns
from iboomto.storage import ApiFailure, Sheets

START, END = date(2026, 10, 10), date(2026, 10, 16)
NOW = datetime(2026, 10, 22, 8, tzinfo=timezone.utc)
PROPS = [{'id': str(index + 100), 'language': lang} for index, lang in enumerate(LANGS)]


class MemoryStore(Sheets):
    def __init__(self):
        self.cache = {}
        self.headers = {}

    def read(self, name):
        return self.cache.setdefault(name, [])

    def set(self, name, rows, headers=None):
        self.cache[name] = list(rows)
        self.headers[name] = headers


def api_for(events=('software_download',), failed=None, metadata=None):
    api = Mock()
    api.ga_timezone.return_value = 'America/Los_Angeles'

    def ga(pid, start, end, dimensions, metrics, filters):
        if failed == (pid, tuple(dimensions)):
            raise RuntimeError('transport error')
        rows = []
        for event in events:
            selection = [expression for expression in filters['andGroup']['expressions'][1:]
                         if 'orGroup' in expression or expression.get('filter', {}).get('fieldName') == 'eventName']
            if selection:
                expression = selection[0]
                if 'orGroup' in expression:
                    terms = [item['filter']['stringFilter']['value'] for item in expression['orGroup']['expressions']]
                    if not any(term.lower() in event.lower() for term in terms):
                        continue
                elif event not in expression['filter']['inListFilter']['values']:
                    continue
            count = 10 if pid == '100' else 90
            sessions = 2 if pid == '100' else 10
            row = {'eventName': event, 'eventCount': count, 'activeUsers': 3,
                   'sessions': sessions, 'eventsPerSession': count / sessions}
            if 'landingPage' in dimensions:
                row['landingPage'] = '/entry'
                row['activeUsers'] = 900  # Detail rows must not affect totals.
            if 'pageLocation' in dimensions:
                row['pageLocation'] = 'https://www.iboomto.com/tool?source=example'
                row['activeUsers'] = 800
            rows.append(row)
        return rows, metadata or {}

    api.ga.side_effect = ga
    return api


class EventCheckTests(unittest.TestCase):
    def test_session_channel_filter_is_exact_and_applies_to_all_views(self):
        api = api_for()
        fetch_property(api, PROPS[0], START, END, NOW,
                       Selection.parse('download|install', 'contains'), 'run', 'Organic Search')
        for call in api.ga.call_args_list:
            expressions = call.args[5]['andGroup']['expressions']
            self.assertEqual(len(expressions), 3)
            self.assertIn('orGroup', expressions[1])
            self.assertEqual(expressions[2], {'filter': {
                'fieldName': 'sessionDefaultChannelGroup', 'stringFilter': {
                    'matchType': 'EXACT', 'value': 'Organic Search', 'caseSensitive': True}}})
        self.assertEqual(len(Selection().filters('all')['andGroup']['expressions']), 1)
        self.assertIn('AI Assistant', CHANNELS)
        with self.assertRaises(ValueError):
            run_check(api, MemoryStore(), PROPS, START, END, Selection(), NOW, 'run', channel='unknown')

    def test_channel_scopes_coexist_and_legacy_all_ids_are_preserved(self):
        store = MemoryStore()
        run_check(api_for(), store, PROPS, START, END, Selection(), NOW, 'legacy')
        original_ids = {tab: {row['id'] for row in store.read(tab)} for tab in VIEWS}
        for tab in VIEWS:
            for row in store.read(tab):
                row.pop('channel')  # Historical reports had no channel column.
        run_check(api_for(), store, PROPS, START, END, Selection(), NOW, 'organic', channel='Organic Search')
        for tab in VIEWS:
            all_rows = [row for row in store.read(tab) if row['channel'] == 'all']
            self.assertEqual({row['id'] for row in all_rows}, original_ids[tab])
            self.assertTrue(all(row['run_id'] == 'legacy' for row in all_rows))
            self.assertEqual(len(all_rows), len([row for row in store.read(tab) if row['channel'] == 'Organic Search']))
        legacy_id = digest(['event-check-v1', SUMMARY, '100', str(START), str(END), 'software_download', ''])
        self.assertIn(legacy_id, original_ids[SUMMARY])
        run_check(api_for(), store, PROPS, START, END, Selection(), NOW, 'organic-again', channel='Organic Search')
        run_check(api_for(), store, PROPS, START, END, Selection(), NOW, 'all-again')
        self.assertEqual(len(store.read(SUMMARY)), 20)
        for tab in VIEWS:
            self.assertEqual(len(store.read(tab)), len({row['id'] for row in store.read(tab)}))
        organic_total = next(row for row in store.read(SUMMARY) if row['channel']=='Organic Search' and row['language']=='all')
        self.assertEqual(organic_total['eventCount'], 730)
        self.assertAlmostEqual(organic_total['eventsPerSession'], 730 / 82)

    def test_channel_failure_does_not_mark_other_channel_totals_failed(self):
        store = MemoryStore()
        run_check(api_for(), store, PROPS, START, END, Selection(), NOW, 'all')
        report = run_check(api_for(failed=('100', ('eventName',))), store, PROPS,
                           START, END, Selection(), NOW, 'failed-organic', channel='Organic Search')
        self.assertEqual(report['channel'], 'Organic Search')
        totals = [row for row in store.read(SUMMARY) if row['language']=='all']
        self.assertEqual(next(row for row in totals if row['channel']=='all')['data_status'], 'returned')
        self.assertEqual(next(row for row in totals if row['channel']=='Organic Search')['data_status'], 'refresh_failed')
        mixed = [fetch_property(api_for(), prop, START, END, NOW, Selection(), 'mixed') for prop in PROPS]
        mixed[0][SUMMARY][0]['channel'] = 'Referral'
        with self.assertRaises(ValueError):
            aggregate(mixed, START, END, Selection(), 'mixed')

    def test_appended_channel_column_extends_filter_and_preserves_user_criteria(self):
        store = Mock()
        store.base = 'https://sheets.googleapis.com/v4/spreadsheets/test'
        store.headers = {SUMMARY: headers(SUMMARY)}
        basic = {'range': {'sheetId': 1, 'startRowIndex': 0, 'endColumnIndex': len(headers(SUMMARY))-1},
                 'filterSpecs': [{'columnIndex': 4, 'filterCriteria': {'hiddenValues': ['en']}}],
                 'criteria': {'4': {'hiddenValues': ['en']}},
                 'sortSpecs': [{'dimensionIndex': 0, 'sortOrder': 'ASCENDING'}]}
        meta = {'sheets': [{'properties': {'title': SUMMARY}, 'basicFilter': basic},
                           {'properties': {'title': 'Properties'}, 'basicFilter': basic}]}
        with patch('iboomto.storage.request', return_value=Mock(json=lambda: meta)) as request:
            extend_report_filters(store)
        body = request.call_args.kwargs['json']['requests']
        self.assertEqual(len(body), 1)
        updated = body[0]['setBasicFilter']['filter']
        self.assertEqual(updated['filterSpecs'], basic['filterSpecs'])
        self.assertEqual(updated['sortSpecs'], basic['sortSpecs'])
        self.assertEqual(updated['range']['endColumnIndex'], len(headers(SUMMARY)))
        self.assertEqual(basic['range']['endColumnIndex'], len(headers(SUMMARY))-1)
        meta['sheets'][0]['basicFilter'] = updated
        with patch('iboomto.storage.request', return_value=Mock(json=lambda: meta)) as request:
            extend_report_filters(store)
        self.assertEqual(request.call_count, 1)  # An unchanged filter needs only the read.

    def test_exact_and_contains_filters_and_literal_or_matching(self):
        exact = Selection.parse('software_download|software_download')
        self.assertTrue(exact.matches('software_download'))
        self.assertFalse(exact.matches('Software_Download'))
        self.assertFalse(exact.matches('software_download_start'))
        self.assertEqual(exact.filters()['andGroup']['expressions'][1]['filter']['inListFilter'],
                         {'values': ['software_download'], 'caseSensitive': True})
        contains = Selection.parse('DOWNLOAD|install|Download', 'contains')
        self.assertTrue(contains.matches('Software_Download'))
        self.assertTrue(contains.matches('pre_install_done'))
        self.assertFalse(contains.matches('page_view'))
        self.assertEqual(len(contains.filters()['andGroup']['expressions'][1]['orGroup']['expressions']), 2)
        self.assertFalse(Selection.parse('down.*', 'contains').matches('download'))
        for value in ('', 'all', ' ALL '):
            self.assertTrue(Selection.parse(value).matches('anything'))
            self.assertEqual(len(Selection.parse(value).filters()['andGroup']['expressions']), 1)
        for value in ('all|download', '|||'):
            with self.assertRaises(ValueError):
                Selection.parse(value)

    def test_spaces_and_commas_separate_multiple_events(self):
        expected = Selection.parse('clickwin|clicktip', 'contains')
        for value in ('clickwin clicktip', 'clickwin,clicktip', ' clickwin,\tclicktip\nclickwin '):
            self.assertEqual(Selection.parse(value, 'contains'), expected)
        store = MemoryStore()
        # Older versions incorrectly queried this whole phrase and stored coverage.
        legacy = Selection(('clickwin clicktip',), 'contains')
        run_check(api_for(()), store, PROPS, START, END, legacy, NOW, 'old')
        run_check(api_for(('clickwin_start', 'clicktip_done')), store, PROPS,
                  START, END, Selection.parse('clickwin clicktip', 'contains'), NOW, 'new')
        for tab in VIEWS:
            self.assertTrue(all(row['data_status'] == 'returned' for row in store.read(tab)))
            self.assertEqual({row['event_name'] for row in store.read(tab)}, {'clickwin_start', 'clicktip_done'})

    def test_direct_whole_range_queries_have_independent_page_dimensions(self):
        api = api_for()
        staged = fetch_property(api, PROPS[0], START, END, NOW, Selection(), 'run')
        self.assertEqual(api.ga.call_count, 3)
        self.assertEqual([call.args[3] for call in api.ga.call_args_list],
                         [['eventName'], ['eventName', 'landingPage'], ['eventName', 'pageLocation']])
        for call in api.ga.call_args_list:
            self.assertEqual(call.args[1:3], (START, END))
            self.assertEqual(call.args[4], METRICS)
            self.assertEqual(call.args[5]['andGroup']['expressions'][0]['filter'],
                             {'fieldName': 'hostName', 'stringFilter': {'matchType': 'EXACT', 'value': 'www.iboomto.com'}})
            self.assertEqual(call.kwargs, {})
        self.assertEqual(staged[SUMMARY][0]['activeUsers'], 3)
        self.assertEqual(staged['Event Check Landing Pages'][0]['landing_page'], '/entry')
        self.assertTrue(staged['Event Check Event Pages'][0]['event_page'].endswith('?source=example'))

    def test_all_language_sums_and_weighted_rate_use_only_fresh_summary(self):
        store = MemoryStore()
        report = run_check(api_for(), store, PROPS, START, END, Selection(), NOW, 'one')
        self.assertEqual(report['status'], 'success')
        rows = store.read(SUMMARY)
        self.assertEqual(len(rows), 10)
        total = next(row for row in rows if row['language'] == 'all')
        self.assertEqual(total['eventCount'], 730)
        self.assertEqual(total['activeUsers'], 27)
        self.assertEqual(total['sessions'], 82)
        self.assertAlmostEqual(total['eventsPerSession'], 730 / 82)
        self.assertNotEqual(total['eventsPerSession'], (5 + 8 * 9) / 9)
        self.assertIn('not deduplicated', total['aggregation_note'])
        self.assertEqual(set(total['metadata']['languages_queried']), set(LANGS))
        for tab in list(VIEWS)[1:]:
            self.assertEqual(len(store.read(tab)), 9)
            self.assertFalse(any(row['language'] == 'all' for row in store.read(tab)))

    def test_same_run_and_overlapping_filters_do_not_duplicate_and_remove_stale_events(self):
        store = MemoryStore()
        run_check(api_for(('software_download', 'page_view')), store, PROPS, START, END, Selection(), NOW, 'one')
        run_check(api_for(('software_download',)), store, PROPS, START, END,
                  Selection.parse('download', 'contains'), NOW, 'two')
        self.assertEqual(len(store.read(SUMMARY)), 20)
        run_check(api_for(()), store, PROPS, START, END, Selection.parse('download', 'contains'), NOW, 'three')
        returned = [row for row in store.read(SUMMARY) if row['data_status'] == 'returned']
        self.assertEqual({row['event_name'] for row in returned}, {'page_view'})
        run_check(api_for(('page_view',)), store, PROPS, START, END, Selection(), NOW, 'four')
        run_check(api_for(('page_view',)), store, PROPS, START, END, Selection(), NOW, 'five')
        self.assertEqual(len(store.read(SUMMARY)), 10)
        self.assertEqual({row['event_name'] for row in store.read(SUMMARY)}, {'page_view'})

    def test_single_language_preserves_other_languages_ranges_and_total(self):
        store = MemoryStore()
        run_check(api_for(), store, PROPS, START, END, Selection(), NOW, 'one')
        prior = copy.deepcopy([row for row in store.read(SUMMARY) if row['language'] != 'en'])
        run_check(api_for(), store, PROPS, START, END, Selection(), NOW, 'two', 'en')
        self.assertEqual([row for row in store.read(SUMMARY) if row['language'] != 'en'], prior)
        run_check(api_for(), store, PROPS, START, START, Selection(), NOW, 'three', 'en')
        self.assertEqual(len(store.read(SUMMARY)), 11)

    def test_failed_view_preserves_all_old_views_for_property_and_marks_total_stale(self):
        store = MemoryStore()
        run_check(api_for(), store, PROPS, START, END, Selection(), NOW, 'one')
        before = {tab: copy.deepcopy([row for row in store.read(tab) if row['language'] == 'en']) for tab in VIEWS}
        report = run_check(api_for(failed=('100', ('eventName', 'pageLocation'))), store,
                           PROPS, START, END, Selection(), NOW, 'two')
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['failed_languages'], ['en'])
        for tab in VIEWS:
            self.assertEqual([row for row in store.read(tab) if row['language'] == 'en'], before[tab])
        total = next(row for row in store.read(SUMMARY) if row['language'] == 'all')
        self.assertEqual(total['data_status'], 'refresh_failed')
        self.assertEqual(total['run_id'], 'one')
        self.assertEqual(total['eventCount'], 730)
        self.assertEqual(total['last_attempt_run_id'], 'two')
        run_check(api_for(), store, PROPS, START, END, Selection(), NOW, 'three')
        total = next(row for row in store.read(SUMMARY) if row['language'] == 'all')
        self.assertEqual(total['data_status'], 'returned')
        self.assertNotIn('refresh_error', total)

    def test_failed_first_run_does_not_publish_partial_total(self):
        store = MemoryStore()
        run_check(api_for(failed=('100', ('eventName',))), store, PROPS, START, END, Selection(), NOW, 'one')
        total = next(row for row in store.read(SUMMARY) if row['language'] == 'all')
        self.assertEqual(total['data_status'], 'refresh_failed')
        self.assertEqual(total['eventCount'], '')

    def test_empty_responses_are_coverage_not_invented_zero_metrics(self):
        store = MemoryStore()
        run_check(api_for(()), store, PROPS, START, END, Selection(), NOW, 'one')
        for tab in VIEWS:
            for row in store.read(tab):
                self.assertEqual(row['data_status'], 'no_data_returned')
                self.assertEqual(row['event_name'], '')
                self.assertTrue(all(row[key] == '' for key in METRICS))

    def test_quality_propagates_even_from_language_without_event_and_mixed_timezones(self):
        results = [fetch_property(api_for(metadata={'subjectToThresholding': True} if prop['language'] == 'en' else {}),
                                  prop, START, END, NOW, Selection(), 'run') for prop in PROPS]
        results[0][SUMMARY][0].update(event_name='', data_status='no_data_returned', timezone='Asia/Tokyo')
        total = aggregate(results, START, END, Selection(), 'run')[SUMMARY][0]
        self.assertEqual(total['quality'], 'limited')
        self.assertEqual(total['timezone'], 'mixed (property local dates)')
        self.assertEqual(len(total['metadata']['languages_returning_event']), 8)
        with self.assertRaises(ValueError):
            aggregate(results[:-1], START, END, Selection(), 'run')

    def test_dates_launch_and_zero_sessions(self):
        api = api_for()
        with self.assertRaises(ValueError):
            fetch_property(api, PROPS[0], END, START, NOW, Selection(), 'run')
        with self.assertRaises(ValueError):
            fetch_property(api, PROPS[0], START, date(2026, 10, 23), NOW, Selection(), 'run')
        api.ga.assert_not_called()
        rows = fetch_property(api, PROPS[0], date(2026, 9, 1), date(2026, 9, 8), NOW, Selection(), 'run')
        self.assertEqual(api.ga.call_args.args[1], LAUNCH)
        self.assertEqual(rows[SUMMARY][0]['quality'], 'partial_launch')
        today = fetch_property(api, PROPS[0], NOW.date(), NOW.date(), NOW, Selection(), 'run')
        self.assertEqual(today[SUMMARY][0]['quality'], 'provisional')
        api.reset_mock()
        prelaunch = fetch_property(api, PROPS[0], date(2026, 9, 1), date(2026, 9, 2), NOW, Selection(), 'run')
        api.ga.assert_not_called()
        self.assertEqual(prelaunch[SUMMARY][0]['data_status'], 'prelaunch')
        results = [fetch_property(api_for(), prop, START, END, NOW, Selection(), 'run') for prop in PROPS]
        for result in results:
            result[SUMMARY][0]['sessions'] = 0
        self.assertEqual(aggregate(results, START, END, Selection(), 'run')[SUMMARY][0]['eventsPerSession'], '')

    def test_ga4_paginates_without_truncating_events(self):
        session = Mock()
        def response(event, metadata=None):
            result = Mock(status_code=200)
            result.json.return_value = {'rowCount': 2, 'metadata': metadata or {}, 'rows': [
                {'dimensionValues': [{'value': event}], 'metricValues': [{'value': '5'}]}]}
            return result
        session.request.side_effect = [response('first', {'subjectToThresholding': True, 'dataLossFromOtherRow': True,
                                                        'samplingMetadatas': [{'samplesReadCount': '10'}]}),
                                       response('second', {'subjectToThresholding': False})]
        rows, meta = Analytics(session).ga('123', START, END, ['eventName'], ['eventCount'])
        self.assertEqual([row['eventName'] for row in rows], ['first', 'second'])
        self.assertEqual(session.request.call_count, 2)
        self.assertTrue(meta['subjectToThresholding'])
        self.assertTrue(meta['dataLossFromOtherRow'])
        self.assertTrue(meta['samplingMetadatas'])

    def test_report_layout_has_filters_and_numeric_rate_format(self):
        for tab in VIEWS:
            head = headers(tab)
            rules = format_columns(123, tab, head, 10, True)
            self.assertTrue(any('setBasicFilter' in rule for rule in rules))
            index = head.index('eventsPerSession')
            rate = next(rule['repeatCell'] for rule in rules if 'repeatCell' in rule and
                        rule['repeatCell']['range']['startColumnIndex'] == index)
            self.assertEqual(rate['cell']['userEnteredFormat']['numberFormat'], {'type': 'NUMBER', 'pattern': '0.00'})

    def test_write_failure_keeps_audit_artifact_and_summary(self):
        store = MemoryStore()
        store.cache['Properties'] = [{'Platform': 'GA', 'Language': p['language'], 'ID': p['id']} for p in PROPS]
        store.flush = Mock(side_effect=ApiFailure('HTTP 400'))
        store.link = Mock(return_value='https://docs.google.com/spreadsheets/d/test/edit')
        result = {'status': 'success', 'failed_languages': [], 'statuses': [], 'rows': {SUMMARY: 1}}
        runtime = Path(__file__).resolve().parent.parent / 'runtime'
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as folder:
            output = Path(folder) / 'audit.json'
            summary = Path(folder) / 'summary.md'
            argv = ['event-check', '--start', str(START), '--end', str(END), '--write', '--output', str(output)]
            with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(summary)}), \
                    patch('iboomto.storage.google_session'), patch('iboomto.storage.Sheets', return_value=store), \
                    patch('iboomto.event_check.run_check', return_value=result):
                self.assertEqual(main(), 1)
            audit = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(audit['status'], 'failed')
            self.assertEqual(audit['write_status'], 'failed')
            self.assertEqual(audit['write_error'], {'error_type': 'ApiFailure', 'message': 'HTTP 400'})
            self.assertEqual(audit['rows'], {SUMMARY: 1})
            self.assertIn('Sheets write failed: HTTP 400', summary.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
