import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from iboomto.core import SITE
from iboomto.analytics import InspectionFailure
from iboomto.inspection_execution import inspect_batch, inspect_one, provenance
from iboomto.inspection_history import merge_observation
from iboomto.manual_inspection import (REMINDER, execute, main, regex_filter,
                                       select_urls, summary, validate_inputs)


class Store:
    def __init__(self, tabs=None):
        self.tabs = tabs or {}
        self.writes = []

    def read(self, tab):
        return self.tabs.get(tab, [])

    def upsert(self, tab, rows):
        self.writes.append((tab, list(rows)))

    def flush(self):
        pass


class API:
    def inspection(self, url):
        return {'indexStatusResult': {'verdict': 'PASS', 'coverageState': 'Indexed'}}


class ManualSelectionTests(unittest.TestCase):
    def test_exact_lists_and_duplicates(self):
        a, b = SITE + '/es/a', SITE + '/es/b'
        self.assertEqual(validate_inputs(f'{a}, {b}\n{a}\r\n', '', 'es'), [a, b])

    def test_invalid_entries_and_language_conflicts(self):
        for url in ['https://evil.example/a', SITE + '.evil/a', SITE + '/a?q=x',
                    'http://www.iboomto.com/a', SITE + '/a#b', SITE + '/app.exe',
                    SITE + '/es/a', 'not a URL']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_inputs(url, '', 'en')

    def test_mutual_exclusion_and_invalid_patterns(self):
        with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
            validate_inputs(SITE, 'blog', 'all')
        with self.assertRaisesRegex(ValueError, 'Invalid URL regex'):
            validate_inputs('', '[', 'all')

    def test_deduplicated_union_and_freshness(self):
        store = Store({'Sitemap URLs': [{'url': SITE + '/es/a', 'observed_at': '2026-10-01'}],
                       'Page name - manual management': [{'Urls': SITE + '/es/b'}, {'Urls': 'bad'}],
                       'URL Inspection': [{'url': SITE + '/es/a'}, {'url': SITE + '/c'}]})
        urls, fresh = select_urls(store, [], '', 'all')
        self.assertEqual(urls, sorted([SITE + '/es/a', SITE + '/es/b', SITE + '/c']))
        self.assertEqual(fresh[0]['latest_observation'], '2026-10-01')
        self.assertEqual(fresh[1]['rows_without_timestamp'], 1)
        self.assertEqual(fresh[1]['invalid_rows_skipped'], 1)

    def test_language_filters_before_regex(self):
        store = Store({'Sitemap URLs': [{'url': SITE + '/es/blog/a'}, {'url': SITE + '/ja/blog/a'}]})
        with patch('iboomto.manual_inspection.regex_filter', side_effect=lambda urls, pattern: urls) as regex:
            urls, _ = select_urls(store, [], '/blog/', 'es')
        regex.assert_called_once_with([SITE + '/es/blog/a'], '/blog/')
        self.assertEqual(urls, [SITE + '/es/blog/a'])

    def test_regex_search_case_sensitive_and_empty(self):
        urls = [SITE + '/blog/a', SITE + '/how-to/b', SITE + '/Blog/c']
        self.assertEqual(regex_filter(urls, '/blog/|/how-to/'), urls[:2])
        self.assertEqual(regex_filter(urls, '/absent/'), [])

    def test_regex_timeout(self):
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'evaluation exceeded'):
            regex_filter([SITE + '/' + 'a' * 10000 + '!'], '(a+)+$', timeout=.5)
        self.assertLess(time.monotonic() - started, 5)

    def test_explicit_ceiling_after_deduplication(self):
        urls = [SITE + '/p/' + str(i) for i in range(1001)]
        self.assertEqual(len(validate_inputs(','.join(urls[:1000] * 2), '', 'all')), 1000)
        with self.assertRaisesRegex(ValueError, '1,001 URLs selected'):
            validate_inputs(','.join(urls), '', 'all')

    def test_inventory_ceiling_after_language_and_regex(self):
        store = Store({'Sitemap URLs': [{'url': SITE + '/es/' + str(i)} for i in range(1001)] +
                       [{'url': SITE + '/ja/a'}]})
        self.assertEqual(len(select_urls(store, [], '/es/[0-9]{1,3}$', 'es')[0]), 1000)
        self.assertEqual(select_urls(store, [], '', 'ja')[0], [SITE + '/ja/a'])
        with self.assertRaisesRegex(ValueError, 'Narrow the language or regex'):
            select_urls(store, [], '', 'es')

    def test_invalid_regex_before_authentication(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, patch.dict(os.environ, {
                'INPUT_URLS': '', 'INPUT_LANGUAGE': 'all', 'INPUT_URL_REGEX': '[',
                'GITHUB_STEP_SUMMARY': ''}), patch('iboomto.storage.google_session') as auth:
            previous = os.getcwd()
            try:
                os.chdir(directory)
                self.assertEqual(main(), 1)
                report = json.loads(Path('runtime/manual-url-inspection.json').read_text())
                self.assertIn('Invalid URL regex', report['message'])
                auth.assert_not_called()
            finally:
                os.chdir(previous)


class ManualExecutionTests(unittest.TestCase):
    def report(self, urls):
        return {'results': [], 'successful': 0, 'failed': 0, 'unchecked_urls': list(urls)}

    def test_empty_selection_has_no_inspection_writes(self):
        store, report = Store(), self.report([])
        execute(store, API, [], {}, report, lambda: None)
        self.assertEqual(report['message'], 'No matching URLs')
        self.assertEqual(store.writes, [])

    def test_failure_preserves_history_and_updates_provenance(self):
        url = SITE + '/a'
        old, _ = merge_observation({}, {'id': url, 'url': url, 'verdict': 'PASS',
            'api_status': 'success', 'checked_at': '2026-10-01T00:00:00+00:00'})
        old['observation_tracking_version'] = 'v1'
        class FailedAPI:
            def inspection(self, url):
                raise InspectionFailure(403)
        origin = {'trigger_type': 'manual', 'run_id': '123', 'run_url': 'https://github.com/x/y/actions/runs/123'}
        store, report = Store({'URL Inspection': [old]}), self.report([url])
        execute(store, FailedAPI, [url], origin, report, lambda: None)
        latest = store.writes[0][1][0]
        self.assertEqual(latest['first_observed_indexed_at'], old['checked_at'])
        self.assertEqual(latest['last_successful_checked_at'], old['checked_at'])
        self.assertEqual(latest['verdict'], 'PASS')
        self.assertEqual(latest['trigger_type'], 'manual')
        self.assertEqual(latest['run_id'], '123')
        self.assertFalse(any(tab == 'URL Inspection History' for tab, _ in store.writes))
        self.assertEqual(report['status'], 'failed')

    def test_permission_and_quota_stop_dispatch(self):
        for status in (401, 403, 429):
            class FailedAPI:
                def inspection(self, url):
                    raise InspectionFailure(status)
            urls = [SITE + '/' + str(i) for i in range(20)]
            rows = []
            unchecked, reason = inspect_batch(urls, FailedAPI, {}, rows.append)
            self.assertLessEqual(len(rows), 4)
            self.assertGreaterEqual(len(rows), 1)
            self.assertEqual(len(unchecked) + len(rows), 20)
            self.assertEqual(reason, 'permission_or_quota_exhaustion')

    def test_normal_failure_does_not_stop_remaining_requests(self):
        class MixedAPI(API):
            def inspection(self, url):
                if url.endswith('/a'):
                    raise InspectionFailure(500)
                return super().inspection(url)
        rows = []
        unchecked, reason = inspect_batch([SITE + '/a', SITE + '/b'], MixedAPI, {}, rows.append)
        self.assertEqual(unchecked, [])
        self.assertEqual(reason, '')
        self.assertEqual(sorted(r['api_status'] for r in rows), ['failed', 'success'])

    def test_completed_results_survive_quota_stop(self):
        class QuotaAPI(API):
            def inspection(self, url):
                if url.endswith('/b'):
                    raise InspectionFailure(429)
                return super().inspection(url)
        rows = []
        urls = [SITE + '/' + x for x in 'abc']
        unchecked, _ = inspect_batch(urls, QuotaAPI, {}, rows.append, max_workers=1)
        self.assertEqual([r['api_status'] for r in rows], ['success', 'failed'])
        self.assertEqual(unchecked, urls[2:])

    def test_new_baseline_has_provenance_and_manual_bypasses_cooldowns(self):
        url, origin = SITE + '/a', {'trigger_type': 'manual', 'run_id': '123', 'run_url': 'run'}
        store, report = Store(), self.report([url])
        execute(store, API, [url], origin, report, lambda: None)
        history = next(rows for tab, rows in store.writes if tab == 'URL Inspection History')
        self.assertEqual(history[0]['run_id'], '123')
        latest = next(rows for tab, rows in store.writes if tab == 'URL Inspection')
        store = Store({'URL Inspection': latest})
        report = self.report([url])
        execute(store, API, [url], origin, report, lambda: None)
        self.assertEqual(report['successful'], 1)
        self.assertFalse(any(tab == 'URL Inspection History' for tab, _ in store.writes))

    def test_scheduled_provenance_and_transition(self):
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'schedule', 'GITHUB_REPOSITORY': 'owner/repo'}):
            origin = provenance('456')
        self.assertEqual(origin['trigger_type'], 'scheduled')
        current = inspect_one(API(), SITE + '/a', origin)
        _, history = merge_observation({'last_known_index_state': 'not_indexed'}, current)
        self.assertEqual(history['trigger_type'], 'scheduled')
        self.assertTrue(history['run_url'].endswith('/actions/runs/456'))

    def test_retained_baseline_keeps_unknown_provenance(self):
        url = SITE + '/a'
        store = Store({'URL Inspection': [{'id': url, 'url': url, 'verdict': 'PASS',
            'api_status': 'success', 'checked_at': '2026-10-01T00:00:00Z'}]})
        execute(store, API, [url], provenance('123', 'manual'), self.report([url]), lambda: None)
        history = next(rows for tab, rows in store.writes if tab == 'URL Inspection History')
        self.assertEqual(history[0]['observation_basis'], 'retained_snapshot')
        self.assertNotIn('run_id', history[0])

    def test_summary_contains_guidance_counts_jst_and_safe_details(self):
        report = {**self.report([]), 'started_at': '2026-10-01T00:00:00+00:00',
                  'status': 'success', 'selected': 0, 'selection': {'url_regex': '<script>'}, 'inventory': []}
        text = summary(report, 'https://example.com')
        self.assertIn(REMINDER, text)
        self.assertIn('09:00:00+09:00', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertIn('Unchecked: **0**', text)
