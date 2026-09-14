import unittest
from collections import Counter
from iboomto.core import LANGS, SITE, language
from iboomto.inspection import select_inspection_urls


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
        self.assertEqual(selected, [manual, new, oldest])

    def test_hard_ceiling(self):
        urls = [SITE + '/a/' + str(i) for i in range(150)]
        self.assertEqual(len(select_inspection_urls(urls, {}, set(), 1000)), 100)
