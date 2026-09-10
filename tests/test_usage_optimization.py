import unittest,json
from datetime import date
from unittest.mock import Mock,patch
from test_monitor import MemoryStore
from iboomto.evidence_selection import latest_comparisons,query_evidence
from iboomto.llm_usage import cost
from iboomto.reporting import ai_analyse
from iboomto.api_usage import Meter,category


class OptimizationTests(unittest.TestCase):
    def test_daily_summary_preserves_full_union_and_major_alerts(self):
        rows=[{'query':str(i),'language':'en','start':'2026-09-20','end':'2026-09-20','clicks':i,'impressions':i*2,
               'selection_reason':'top100_clicks','baseline_status':'returned'} for i in range(300)]
        rows[0]['severity']='red'
        summary,details=query_evidence(rows,'daily')
        self.assertEqual(summary[0]['selected_query_count'],300)
        self.assertEqual(summary[0]['selected_query_clicks'],sum(range(300)))
        self.assertLess(len(details),25)
        self.assertIn('0',{r['query'] for r in details})
        self.assertEqual(len(query_evidence(rows,'weekly')[1]),300)
        self.assertEqual(len(query_evidence(rows[:7],'daily')[1]),7)

    def test_comparisons_keep_independent_source_dates_and_both_baselines(self):
        rows=[{'source':'GA4 Site','language':'en','period':'daily','current_end':'2026-09-19','comparison':'day_over_day'},
              {'source':'GA4 Site','language':'en','period':'daily','current_end':'2026-09-20','comparison':'day_over_day'},
              {'source':'GA4 Site','language':'en','period':'daily','current_end':'2026-09-20','comparison':'same_weekday'},
              {'source':'GSC Site','language':'en','period':'daily','current_end':'2026-09-18'}]
        result=latest_comparisons(rows)
        self.assertEqual(len(result),3)
        self.assertIn(rows[-1],result)

    def test_price_uses_disjoint_cache_buckets_and_no_reasoning_double_count(self):
        usage={'prompt_tokens':1000,'completion_tokens':200,'prompt_tokens_details':{'cached_tokens':200,'cache_write_tokens':500},'completion_tokens_details':{'reasoning_tokens':100}}
        self.assertAlmostEqual(cost(usage,'gpt-5.6-sol',date(2026,9,10))['estimated_cost_usd'],.00778)
        self.assertEqual(cost(usage,'other-model')['estimated_cost_usd'],'')
        self.assertEqual(cost(usage,'gpt-5.6-sol',date(2026,12,1))['estimated_cost_usd'],'')

    def test_attempts_are_audited_and_cached_calls_cost_zero(self):
        report=MemoryStore();result={'summary':'ok','findings':[],'actions':[],'deep_analysis_candidates':[],'limitations':[]}
        response=Mock(status_code=200);response.json.return_value={'id':'test','model':'gpt-5.6-sol','usage':{'prompt_tokens':100,'completion_tokens':20},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}
        with patch.dict('os.environ',{'OPENAI_API_KEY':'test','IBOOMTO_AI_REPORTS_ENABLED':'true'}),patch('iboomto.llm_usage.token_estimates',return_value={'estimated_input_tokens':90,'module_token_estimates':{}}),patch('iboomto.reporting.requests.post',return_value=response) as post:
            ai_analyse({},report);ai_analyse({},report)
        self.assertEqual(post.call_count,1)
        self.assertEqual(len(report.read('AI Run Usage')),2)
        self.assertEqual(report.read('AI Run Usage')[-1]['api_calls'],0)
        self.assertEqual(report.read('AI Usage')[0]['input_tokens'],100)

    def test_timeout_is_not_retried_or_reported_as_free(self):
        report=MemoryStore()
        with patch.dict('os.environ',{'OPENAI_API_KEY':'test','IBOOMTO_AI_REPORTS_ENABLED':'true'}),patch('iboomto.llm_usage.token_estimates',return_value={}),patch('iboomto.reporting.requests.post',side_effect=TimeoutError) as post:
            with self.assertRaises(TimeoutError):ai_analyse({},report)
        post.assert_called_once()
        self.assertEqual(report.read('AI Run Usage')[0]['unknown_cost_calls'],1)
        self.assertEqual(report.read('AI Run Usage')[0]['estimated_cost_usd'],'')

    def test_partition_calls_and_synthesis_are_counted_in_one_run(self):
        report=MemoryStore();result={'summary':'ok','findings':[],'actions':[],'deep_analysis_candidates':[],'limitations':[]}
        response=Mock(status_code=200);response.json.return_value={'model':'gpt-5.6-sol','usage':{'prompt_tokens':100,'completion_tokens':20},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}
        with patch.dict('os.environ',{'OPENAI_API_KEY':'test','IBOOMTO_AI_REPORTS_ENABLED':'true'}),patch('iboomto.llm_usage.token_estimates',return_value={}),patch('iboomto.reporting.requests.post',return_value=response),patch('iboomto.llm_evidence.evidence_chunks',return_value=[[{'part':1}],[{'part':2}]]):
            ai_analyse({'_compact_schema':'test','long_field':'x'*200001},report)
        self.assertEqual(report.read('AI Run Usage')[0]['api_calls'],3)
        self.assertEqual(report.read('AI Run Usage')[0]['input_tokens_known'],300)
        self.assertEqual([r['phase'] for r in report.read('AI Usage')],['partition','partition','synthesis'])

    def test_google_meter_records_quota_remaining_and_shared_read_write_pacing(self):
        meter=Meter();key=('GA4','runReport','123')
        meter.record(key,200,.2,{'tokensPerDay':{'consumed':5,'remaining':199995}})
        meter.record(key,429,.1)
        row=meter.rows()[0]
        self.assertEqual(row['requests'],2);self.assertEqual(row['http_429'],1)
        self.assertEqual(row['quota']['tokensPerDay']['latest_remaining'],199995)
        self.assertEqual(category('POST','https://www.googleapis.com/webmasters/v3/sites/private/searchAnalytics/query',{'dimensions':['query']}),('GSC','queries','iboomto.com'))
        with patch('iboomto.api_usage.time.monotonic',return_value=10),patch('iboomto.api_usage.time.sleep') as sleep:
            meter.pace(('Sheets','read',''));meter.pace(('Sheets','read',''));meter.pace(('Sheets','write',''))
        sleep.assert_called_once_with(1.3)
