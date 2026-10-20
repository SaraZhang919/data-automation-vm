import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock

from test_monitor import MemoryStore
from iboomto.core import LAUNCH
from iboomto.referral import METRICS, TAB, backfill_ranges, collect_referral

NOW = datetime(2026, 10, 20, 8, tzinfo=timezone.utc)
PROP = {'id': '123', 'language': 'ja'}


def raw(source='example.com', sessions=10, users=7):
    return {'sessionSource': source, 'sessions': sessions, 'activeUsers': users,
            'totalUsers': users, 'newUsers': 2, 'engagedSessions': 6,
            'engagementRate': .6, 'averageSessionDuration': 35.5,
            'eventCount': 42, 'keyEvents': 3}


def api_for(rows, meta=None):
    api = Mock()
    api.ga_timezone.return_value = 'America/Los_Angeles'
    api.ga.return_value = (rows, meta or {})
    return api


class ReferralTests(unittest.TestCase):
    def test_daily_top30_is_selected_independently_per_day(self):
        api = api_for([raw('source-' + str(i), i + 1) for i in range(40)])
        store = MemoryStore()
        result = collect_referral(api, store, PROP, date(2026, 10, 10), date(2026, 10, 11), NOW)
        self.assertEqual(result['requests'], 2)
        self.assertEqual(len(store.read(TAB)), 60)
        for call in api.ga.call_args_list:
            args, kwargs = call
            self.assertEqual(args[1], args[2])
            self.assertEqual(args[3], ['sessionSource'])
            self.assertEqual(kwargs, {'limit': 30, 'order': 'sessions'})
        for day in ('2026-10-10', '2026-10-11'):
            rows = [r for r in store.read(TAB) if r['start'] == day]
            self.assertEqual([r['rank'] for r in rows], list(range(1, 31)))
            self.assertEqual(rows[0]['sessions'], 40)
            self.assertEqual(rows[-1]['sessions'], 11)

    def test_exact_channel_and_production_host_filters(self):
        api, store = api_for([raw()]), MemoryStore()
        collect_referral(api, store, PROP, date(2026, 10, 10), date(2026, 10, 10), NOW)
        filters = api.ga.call_args.args[5]['andGroup']['expressions']
        self.assertEqual(filters[0]['filter'], {'fieldName': 'hostName',
            'stringFilter': {'matchType': 'EXACT', 'value': 'www.iboomto.com'}})
        self.assertEqual(filters[1]['filter'], {'fieldName': 'sessionDefaultChannelGroup',
            'inListFilter': {'values': ['Referral']}})
        row = store.read(TAB)[0]
        self.assertEqual((row['language'], row['channel'], row['property']), ('ja', 'Referral', '123'))
        self.assertEqual(row['session_source'], 'example.com')

    def test_weekly_users_and_rates_come_from_whole_period_api(self):
        api, store = api_for([raw(users=9)]), MemoryStore()
        collect_referral(api, store, PROP, date(2026, 10, 11), date(2026, 10, 17), NOW, 'weekly')
        api.ga.assert_called_once()
        self.assertEqual(api.ga.call_args.args[1:3], (date(2026, 10, 11), date(2026, 10, 17)))
        row = store.read(TAB)[0]
        self.assertEqual(row['activeUsers'], 9)
        self.assertEqual(row['engagementRate'], .6)
        self.assertEqual(row['eventCount'], 42)
        self.assertEqual(row['key_events_per_user'], 3 / 9)
        self.assertEqual(api.ga.call_args.args[4], METRICS)

    def test_launch_month_queries_only_available_dates_but_labels_partial(self):
        api, store = api_for([raw()]), MemoryStore()
        collect_referral(api, store, PROP, date(2026, 9, 1), date(2026, 9, 30), NOW, 'monthly')
        self.assertEqual(api.ga.call_args.args[1], LAUNCH)
        row = store.read(TAB)[0]
        self.assertEqual(row['start'], '2026-09-01')
        self.assertEqual(row['quality'], 'partial_launch')

    def test_reranking_replaces_partition_and_preserves_other_languages(self):
        api, store = api_for([raw('old.example')]), MemoryStore()
        args = (api, store, PROP, date(2026, 10, 11), date(2026, 10, 17), NOW, 'weekly')
        collect_referral(*args)
        other = {**store.read(TAB)[0], 'property': '456', 'language': 'en', 'id': 'other'}
        store.upsert(TAB, [other])
        api.ga.return_value = ([raw('new.example')], {})
        collect_referral(*args)
        self.assertEqual({r['session_source'] for r in store.read(TAB) if r['property'] == '123'}, {'new.example'})
        self.assertIn(other, store.read(TAB))
        collect_referral(*args)
        self.assertEqual(len(store.read(TAB)), 2)

    def test_empty_response_records_coverage_without_inventing_zeros(self):
        api, store = api_for([]), MemoryStore()
        collect_referral(api, store, PROP, date(2026, 10, 10), date(2026, 10, 10), NOW)
        row = store.read(TAB)[0]
        self.assertEqual(row['data_status'], 'no_data_returned')
        self.assertEqual(row['session_source'], '')
        self.assertEqual(row['sessions'], '')
        self.assertEqual(row['activeUsers'], '')

    def test_failed_query_preserves_existing_partition(self):
        api, store = api_for([raw()]), MemoryStore()
        args = (api, store, PROP, date(2026, 10, 10), date(2026, 10, 10), NOW)
        collect_referral(*args)
        original = list(store.read(TAB))
        api.ga.side_effect = RuntimeError('transport failure')
        with self.assertRaises(RuntimeError):
            collect_referral(*args)
        self.assertEqual(store.read(TAB), original)

    def test_backfill_calendar_boundaries(self):
        ranges = backfill_ranges(date(2026, 10, 19))
        self.assertEqual(ranges[0], ('daily', LAUNCH, date(2026, 10, 19)))
        weeks = [r for r in ranges if r[0] == 'weekly']
        self.assertEqual(len(weeks), 6)
        self.assertEqual(weeks[0][1:], (date(2026, 9, 6), date(2026, 9, 12)))
        self.assertEqual(weeks[-1][1:], (date(2026, 10, 11), date(2026, 10, 17)))
        self.assertIn(('monthly', date(2026, 9, 1), date(2026, 9, 30)), ranges)
        self.assertFalse(any(r[0] == 'monthly' and r[1].month == 10 for r in ranges))

    def test_quality_and_utc_observation_time(self):
        api, store = api_for([raw()], {'subjectToThresholding': True}), MemoryStore()
        collect_referral(api, store, PROP, date(2026, 10, 10), date(2026, 10, 10), NOW)
        row = store.read(TAB)[0]
        self.assertEqual(row['quality'], 'limited')
        self.assertTrue(row['collected_at'].endswith('+00:00'))

    def test_current_property_date_and_invalid_range_rejected(self):
        api, store = api_for([]), MemoryStore()
        with self.assertRaisesRegex(ValueError, 'completed dates'):
            collect_referral(api, store, PROP, date(2026, 10, 20), date(2026, 10, 20), NOW)
        with self.assertRaisesRegex(ValueError, 'Start must not exceed'):
            collect_referral(api, store, PROP, date(2026, 10, 19), date(2026, 10, 18), NOW)
        api.ga.assert_not_called()
