import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock

from test_monitor import MemoryStore
from iboomto.ai_traffic import DEFAULT_AI_TRAFFIC_SOURCES, matches, source_rows
from iboomto.collectors import collect_ai_traffic
from iboomto.reporting import initialise_config


class AiTrafficTests(unittest.TestCase):
    def test_default_mapping_matches_known_sources_without_matching_normal_referral(self):
        mappings = source_rows([])
        self.assertEqual(matches({'sessionSource': 'chatgpt.com', 'sessionMedium': 'referral'}, mappings)['id'], 'chatgpt')
        self.assertEqual(matches({'sessionSource': 'perplexity.ai', 'sessionMedium': 'referral'}, mappings)['id'], 'perplexity')
        self.assertIsNone(matches({'sessionSource': 'example.com', 'sessionMedium': 'referral'}, mappings))

    def test_initialise_config_seeds_editable_source_mapping(self):
        store = MemoryStore()
        initialise_config(store)
        self.assertEqual(len(store.read('AI Traffic Sources')), len(DEFAULT_AI_TRAFFIC_SOURCES))
        self.assertEqual(store.read('AI Traffic Sources')[0]['mapping_version'], 'ai-referral-v1')

    def test_ai_collector_writes_exact_total_and_source_rows(self):
        store = MemoryStore()
        store.set('GA4 Site', [
            {'property': '123', 'period': 'daily', 'start': '2026-09-07', 'end': '2026-09-07', 'sessions': 100},
            {'property': '123', 'period': 'daily', 'start': '2026-09-08', 'end': '2026-09-08', 'sessions': 120},
        ])
        api = Mock()
        api.ga_timezone.return_value = 'UTC'

        def ga(pid, start, end, dimensions, metrics, filters, **kwargs):
            if 'sessionSource' in dimensions:
                return ([
                    {'date': '2026-09-07', 'sessionSource': 'chatgpt.com', 'sessionMedium': 'referral',
                     'sessionSourceMedium': 'chatgpt.com / referral', 'sessionDefaultChannelGroup': 'Referral',
                     'sessions': 5, 'activeUsers': 4, 'engagedSessions': 3},
                    {'date': '2026-09-07', 'sessionSource': 'example.com', 'sessionMedium': 'referral',
                     'sessionSourceMedium': 'example.com / referral', 'sessionDefaultChannelGroup': 'Referral',
                     'sessions': 30, 'activeUsers': 20, 'engagedSessions': 15},
                ], {})
            return ([{'date': '2026-09-07', 'sessions': 5, 'activeUsers': 4, 'engagedSessions': 3}], {})

        api.ga.side_effect = ga
        result = collect_ai_traffic(api, store, {'id': '123', 'language': 'en'}, date(2026, 9, 7), date(2026, 9, 8),
                                    datetime(2026, 9, 10, tzinfo=timezone.utc))
        rows = store.read('GA4 AI Traffic')
        total = next(row for row in rows if row['row_type'] == 'total' and row['end'] == '2026-09-07')
        source = next(row for row in rows if row['row_type'] == 'source')
        no_match = next(row for row in rows if row['row_type'] == 'total' and row['end'] == '2026-09-08')
        self.assertEqual(total['sessions'], 5)
        self.assertEqual(total['activeUsers'], 4)
        self.assertEqual(source['ai_source'], 'ChatGPT')
        self.assertEqual(source['sessions'], 5)
        self.assertEqual(no_match['sessions'], 0)
        self.assertEqual(no_match['data_status'], 'returned_no_ai_matches')
        self.assertEqual(result['requests'], 2)


if __name__ == '__main__':
    unittest.main()
