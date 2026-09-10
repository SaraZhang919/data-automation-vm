import unittest
from datetime import datetime, timedelta, timezone, date
from unittest.mock import Mock, patch
from test_monitor import MemoryStore
from iboomto.clarity import collect, slot_start, select_pages, page_rows, ANCHOR
from iboomto.clarity_summary import CORE
from iboomto.llm_evidence import clarity_summary
from iboomto.maintenance import expired


def payload(url=None):
    return [{'metricName': name, 'information': [
        {'totalSessionCount': 15, 'distantUserCount': 12, 'PagesPerSessionPercentage': 2,
         'subTotal': 2, **({'Url': url} if url else {})}]} for name in CORE]


def analytics():
    api = Mock()
    def gsc(start, end, dimensions, **kwargs):
        if dimensions == ['date']:
            return [], {'firstIncompleteDate': '2026-09-08'}, False
        return [{'page': 'https://www.iboomto.com/a', 'clicks': 5}], {}, False
    api.gsc.side_effect = gsc
    return api


class ClarityTests(unittest.TestCase):
    def test_fixed_slots_survive_month_boundary_and_runner_jitter(self):
        self.assertIsNone(slot_start(ANCHOR-timedelta(seconds=1)))
        self.assertEqual(slot_start(ANCHOR+timedelta(hours=47)), ANCHOR)
        self.assertEqual(slot_start(ANCHOR+timedelta(hours=48, minutes=9)), ANCHOR+timedelta(hours=48))
        self.assertEqual(slot_start(datetime(2026,10,1,8,tzinfo=timezone.utc)), datetime(2026,9,30,8,tzinfo=timezone.utc))

    def test_two_requests_per_slot_and_no_duplicate_next_day(self):
        store = MemoryStore(); session = Mock(); session.headers = {}
        session.get.side_effect = [Mock(status_code=200, json=lambda: payload()),
                                   Mock(status_code=200, json=lambda: payload('https://www.iboomto.com/a'))]
        with patch('iboomto.clarity.requests.Session', return_value=session):
            self.assertEqual(collect(store,'test',ANCHOR,analytics())['status'], 'success')
            self.assertEqual(collect(store,'test',ANCHOR+timedelta(hours=24),analytics())['status'], 'cached')
        self.assertEqual([c.kwargs['params'] for c in session.get.call_args_list],
                         [{'numOfDays':3}, {'numOfDays':3,'dimension1':'URL'}])
        self.assertEqual(len(store.read('Clarity Pages')), 1)
        row=store.read('Clarity Pages')[0]
        self.assertEqual(row['pages_per_session'],2)
        self.assertEqual(row['distinct_users'],12)
        self.assertEqual(row['cadence'],'every_48h')

    def test_failed_url_view_retries_without_repeating_overall(self):
        store=MemoryStore();session=Mock();session.headers={}
        session.get.side_effect=[Mock(status_code=200,json=lambda:payload()),Mock(status_code=503),
                                 Mock(status_code=200,json=lambda:payload('https://www.iboomto.com/a'))]
        with patch('iboomto.clarity.requests.Session',return_value=session):
            self.assertEqual(collect(store,'test',ANCHOR,analytics())['status'],'partial')
            self.assertEqual(collect(store,'test',ANCHOR+timedelta(hours=1),analytics())['status'],'success')
        self.assertEqual(session.get.call_count,3)
        self.assertEqual(len(store.read('Clarity Snapshots')),1)

    def test_gsc_uses_completed_boundary_and_click_top20(self):
        api=analytics();rows,selection=select_pages(api,ANCHOR)
        self.assertEqual(selection['gsc_end'],'2026-09-07')
        self.assertEqual(selection['gsc_start'],'2026-09-07')
        call=api.gsc.call_args
        self.assertEqual(call.kwargs,{'state':'final','prefix':'/','limit':20})
        self.assertEqual(call.args[2],['page'])

    def test_missing_and_duplicate_variants_are_not_zero_or_summed(self):
        data=payload('https://www.iboomto.com/a?x=1')
        for item in data:
            item['information'] += [{**item['information'][0],'Url':'https://www.iboomto.com/a?x=2'}]
        selected=[{'page_url':'https://www.iboomto.com/a'},{'page_url':'https://www.iboomto.com/missing'}]
        rows=page_rows(data,selected,{'snapshot_id':'x'})
        self.assertEqual(rows[0]['data_status'],'ambiguous_url_variants')
        self.assertEqual(rows[1]['data_status'],'not_returned')
        self.assertNotIn('total_sessions',rows[0]);self.assertNotIn('total_sessions',rows[1])

    def test_only_latest_page_snapshot_reaches_llm_and_retention_uses_window(self):
        result=clarity_summary([{'window_end':'2026-09-12'}],'weekly',
                               [{'window_end':'2026-09-10','page_url':'old'},
                                {'window_end':'2026-09-12','page_url':'new'}])
        self.assertEqual(result['pages']['count'],1)
        self.assertEqual(result['pages']['common']['page_url'],'new')
        self.assertTrue(expired({'window_end':'2026-09-10'},'Clarity Pages',date(2027,1,1)))

    def test_no_http_before_anchor_or_without_token(self):
        with patch('iboomto.clarity.requests.Session') as session:
            self.assertEqual(collect(MemoryStore(),'test',ANCHOR-timedelta(hours=1))['status'],'scheduled_48h')
            self.assertEqual(collect(MemoryStore(),None,ANCHOR)['status'],'not_configured')
            session.assert_not_called()

