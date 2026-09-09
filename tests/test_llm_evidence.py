import unittest,json
from datetime import datetime,timezone
from unittest.mock import Mock,patch
from test_monitor import MemoryStore
from iboomto.llm_evidence import compact_evidence,comparison_summary,evidence_chunks,dumps
from iboomto.clarity_summary import from_legacy
from iboomto.technical import clarity_collect

class EvidenceTests(unittest.TestCase):
    def test_rule_and_issue_identifiers_remain_interpretable(self):
        result=compact_evidence({'rules':[{'id':'rate-ctr','min_denominator':500}], 'issues':[{'id':'abc','kind':'noindex'}]})
        self.assertEqual(result['rules']['common']['rule_name'],'rate-ctr')
        self.assertEqual(result['issues']['common']['issue_id'],'abc')

    def test_unavailable_comparisons_preserve_counts_without_fake_zero(self):
        rows=[{'comparison_status':'unavailable','source':'GA4 Site','language':'en','metric':'sessions','reason':'baseline_missing','value':i} for i in range(200)]
        result=comparison_summary(rows)
        self.assertEqual(result['available']['count'],0)
        self.assertEqual(result['unavailable_groups']['common']['row_count'],200)
        self.assertIn('baseline_missing',dumps(result))

    def test_clarity_overall_only_preserves_actual_window(self):
        raw=[{'view':'overall','metric':'Traffic','day':'2026-09-09','window_start':'2026-09-08T00:00:00Z','window_end':'2026-09-09T00:00:00Z','window_type':'rolling_24h','data':{'totalSessionCount':'150','distinctUserCount':'99'}},
             {'view':'URL','metric':'Traffic','day':'2026-09-09','data':{'Url':'https://www.iboomto.com/private?email=personal','totalSessionCount':10000}}]
        payload=compact_evidence({'report_period':'daily','clarity':raw})
        row=payload['clarity']['snapshot'];self.assertEqual(row['total_sessions'],150)
        self.assertEqual(row['window_type'],'rolling_24h');self.assertFalse(row['is_full_calendar_week'])
        self.assertNotIn('personal',dumps(payload));self.assertNotIn('10000',dumps(payload))

    def test_other_days_make_no_clarity_request(self):
        with patch('iboomto.technical.requests.Session') as session:
            result=clarity_collect(MemoryStore(),'test',datetime(2026,9,9,8,tzinfo=timezone.utc))
            self.assertEqual(result['status'],'scheduled_weekly');session.assert_not_called()

    def test_tuesday_single_overall_72h_request_and_duplicate_skip(self):
        store=MemoryStore();response=Mock();response.status_code=200
        from iboomto.clarity_summary import CORE
        response.json.return_value=[{'metricName':name,'information':[{'totalSessionCount':'150','subTotal':2,'sessionsWithMetricPercentage':5}]} for name in CORE]
        session=Mock();session.headers={};session.get.return_value=response
        with patch('iboomto.technical.requests.Session',return_value=session):
            first=clarity_collect(store,'test',datetime(2026,9,15,8,tzinfo=timezone.utc))
            second=clarity_collect(store,'test',datetime(2026,9,15,9,tzinfo=timezone.utc))
        self.assertEqual(first['status'],'success');self.assertEqual(second['status'],'cached')
        session.get.assert_called_once();self.assertEqual(session.get.call_args.kwargs['params'],{'numOfDays':3})
        self.assertEqual(len(store.read('Clarity Snapshots')),1)

    def test_columnar_values_quality_and_urls_are_preserved(self):
        p={'report_period':'daily','latest_metrics':[{'language':'en','quality':'provisional','sessions':50,'metadata':{'secret':'x'},'collected_at':'volatile'}],
           'detail_summaries':{'GSC Pages':[{'page_url':'https://www.iboomto.com/a?tracking=private','clicks':3,'quality':'provisional'}]}}
        packed=compact_evidence(p)
        self.assertEqual(packed['site_metrics']['common']['sessions'],50)
        self.assertEqual(packed['details']['GSC Pages']['common']['page_url'],'https://www.iboomto.com/a')
        self.assertNotIn('private',dumps(packed));self.assertNotIn('secret',dumps(packed))
        self.assertIn('provisional',dumps(packed))

    def test_large_nested_tables_not_dropped_in_partitioning(self):
        p={'details':{'GSC Pages':{'columns':['url','clicks'],'common':{'quality':'final'},'count':100,'rows':[['u'+str(i),i] for i in range(100)]}}}
        parts=list(evidence_chunks(p,1000));decoded=[r for batch in parts for r in batch]
        self.assertEqual(len(decoded),100)
        self.assertEqual({r['row'][0] for r in decoded},{'u'+str(i) for i in range(100)})
        self.assertTrue(all(r['table']['columns']==['url','clicks'] and r['table']['common']['quality']=='final' for r in decoded))

if __name__=='__main__':unittest.main()
