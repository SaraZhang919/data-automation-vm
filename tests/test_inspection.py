import unittest
from collections import Counter
from datetime import datetime, timezone
from iboomto.core import LANGS, SITE, language
from iboomto.inspection import select_inspection_urls, needs_index_review


class InspectionSelectionTests(unittest.TestCase):
    def test_independent_language_limits(self):
        urls = [SITE + ('' if lg == 'en' else '/' + lg) + '/essential-tools/a/' + str(i)
                for lg in LANGS for i in range(40)]
        selected = select_inspection_urls(urls, {}, set())
        self.assertEqual(len(selected), 270)
        self.assertEqual(Counter(map(language, selected)), dict.fromkeys(LANGS, 30))

    def test_sparse_language_does_not_donate_slots(self):
        urls = [SITE + '/essential-tools/' + str(i) for i in range(80)]
        urls += [SITE + '/pt', SITE + '/zh-tw', SITE + '/es', SITE + '/es/a',
                 SITE + '/asset.exe', 'https://other.example/a']
        selected = select_inspection_urls(urls, {}, {SITE + '/pt'})
        self.assertEqual(Counter(map(language, selected)), {'en': 30, 'pt': 1, 'zh-tw': 1, 'es': 2})
        self.assertEqual(len(selected), len(set(selected)))

    def test_existing_rotation_and_manual_inclusion(self):
        new = SITE + '/es/new'
        oldest = SITE + '/es/old'
        recent = SITE + '/es/recent'
        manual = SITE + '/es/manual'
        old = {oldest: {'checked_at': '2026-09-07'}, recent: {'checked_at': '2026-09-13'}}
        selected = select_inspection_urls([new, oldest, recent], old, {manual}, 3)
        self.assertEqual(selected, [manual, oldest, new])

    def test_hard_ceiling(self):
        urls = [SITE + '/a/' + str(i) for i in range(150)]
        self.assertEqual(len(select_inspection_urls(urls, {}, set(), 1000)), 100)

    def test_ten_slots_for_each_group(self):
        urls = [SITE + '/' + kind + '/' + str(i) for kind in ('new', 'pending', 'indexed') for i in range(40)]
        old = {u: {'api_status': 'success', 'checked_at': '2026-09-01',
                   'verdict': 'PASS' if '/indexed/' in u else 'NEUTRAL',
                   'coverage_state': 'Crawled - currently not indexed' if '/pending/' in u else 'Indexed'}
               for u in urls if '/new/' not in u}
        selected = select_inspection_urls(urls, old, set(), now=datetime(2026, 9, 14, tzinfo=timezone.utc))
        self.assertEqual(Counter(u.split('/')[-2] for u in selected), {'new': 10, 'pending': 10, 'indexed': 10})

    def test_cooldowns_apply_even_to_spare_slots(self):
        old = {
            SITE + '/pending': {'checked_at': '2026-09-12T08:00:00Z', 'coverage_state': 'Discovered - currently not indexed'},
            SITE + '/due': {'checked_at': '2026-09-11T08:00:00Z', 'coverage_state': 'Discovered - currently not indexed'},
            SITE + '/failed-today': {'checked_at': '2026-09-14T07:00:00Z', 'api_status': 'failed'},
            SITE + '/failed-yesterday': {'checked_at': '2026-09-13T08:00:00Z', 'api_status': 'failed'}}
        selected = select_inspection_urls(old, old, set(), now=datetime(2026, 9, 14, 8, tzinfo=timezone.utc))
        self.assertEqual(set(selected), {SITE + '/due', SITE + '/failed-yesterday'})

    def test_normal_exclusions_do_not_get_priority(self):
        for reason in ('Excluded by noindex tag', 'Page with redirect', 'Alternate page with proper canonical tag', 'Duplicate without user-selected canonical', 'Blocked by robots.txt', 'Soft 404'):
            self.assertFalse(needs_index_review(SITE + '/a', {'verdict': 'NEUTRAL', 'coverage_state': reason}))
        self.assertFalse(needs_index_review(SITE + '/a', {'coverage_state': 'Crawled - currently not indexed', 'google_canonical': SITE + '/b'}))
        self.assertTrue(needs_index_review(SITE + '/a', {'result': '{"indexStatusResult":{"coverageState":"Discovered - currently not indexed"}}'}))

    def test_excluded_pages_remain_in_regular_rotation(self):
        url = SITE + '/noindex'
        self.assertEqual(select_inspection_urls([url], {url: {'coverage_state': 'Excluded by noindex tag'}}, set()), [url])
