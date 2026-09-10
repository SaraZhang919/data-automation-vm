import unittest
from datetime import date
from unittest.mock import Mock,patch
from iboomto.query_selection import select, collect_queries, baseline_range
from iboomto.missing_values import display, internal


def row(q, clicks, impressions):
    return dict(query=q,clicks=clicks,impressions=impressions,ctr=clicks/impressions if impressions else 0,position=10)


class QuerySelectionTests(unittest.TestCase):
    def test_low_click_high_impressions_and_opportunities_survive_union(self):
        rows=[row('click'+str(i),1000-i,1500-i) for i in range(110)]
        rows += [row('exposure',0,10000),row('new',0,10),row('growth',0,25)]
        baseline=[row(r['query'],r['clicks'],r['impressions']*7) for r in rows if r['query']!='new']
        baseline[-1]=row('growth',0,70)
        selected={r['query']:r for r in select(rows,baseline,1,7,'available')}
        self.assertIn('top100_impressions',selected['exposure']['selection_reason'])
        self.assertEqual(selected['new']['selection_reason'],'new_in_candidate_pool')
        self.assertEqual(selected['new']['baseline_impressions'],'')
        self.assertEqual(selected['new']['baseline_status'],'not_returned_in_pool')
        self.assertIn('growing_impressions',selected['growth']['selection_reason'])
        self.assertEqual(selected['growth']['impressions_growth_ratio'],1.5)
        self.assertEqual(len(selected),len(set(selected)))

    def test_partial_or_empty_baseline_never_creates_new_or_growth_labels(self):
        for status in ('insufficient_history','no_baseline_rows'):
            selected=select([row('new',3,100)],[],1,7,status)
            self.assertNotIn('new_in',selected[0]['selection_reason'])
            self.assertEqual(selected[0]['impressions_growth_ratio'],'')

    def test_growth_uses_per_day_rates_and_ignores_tiny_bases(self):
        self.assertNotIn('growing',select([row('same',1,20)],[row('same',7,140)],1,7,'available')[0]['selection_reason'])
        self.assertNotIn('growing',select([row('tiny',1,2)],[row('tiny',0,1)],1,7,'available')[0]['selection_reason'])

    def test_candidate_pool_limit_and_final_only_requests(self):
        api=Mock();api.gsc.return_value=([row('q',2,20)],{'responseAggregationType':'byPage'},False)
        selected,_=collect_queries(api,date(2026,9,14),date(2026,9,14),'daily','en')
        self.assertEqual(len(api.gsc.call_args_list),2)
        self.assertTrue(all(c.kwargs['limit']==5000 and c.args[4]=='final' for c in api.gsc.call_args_list))
        self.assertEqual(selected[0]['baseline_start'],'2026-09-07')
        api.reset_mock()
        collect_queries(api,date(2026,9,7),date(2026,9,7),'daily','en')
        api.gsc.assert_called_once()

    def test_monthly_uses_previous_calendar_month(self):
        self.assertEqual(baseline_range(date(2026,11,1),date(2026,11,30),'monthly'),(date(2026,10,1),date(2026,10,31)))

    def test_display_na_preserves_zero_and_excludes_manual_configuration(self):
        for tab,key in [('GSC Pages','clicks'),('GA4 Landing Pages','page_name'),('Clarity Pages','rage_click_count')]:
            self.assertEqual(display(tab,key,''),'n.a.')
            self.assertEqual(display(tab,key,0),0)
            self.assertEqual(internal(tab,key,'n.a.'),'')
        self.assertEqual(display('Page name - manual management','page_name',''),'')
        self.assertEqual(display('GSC Queries','query',''),'')
        self.assertEqual(display('GSC Pages','id',''),'')

    def test_sheet_reader_decodes_only_supported_fields_before_analysis(self):
        from iboomto.storage import Sheets
        meta={'sheets':[{'properties':{'title':'GSC Queries','sheetId':1,'gridProperties':{'rowCount':10,'columnCount':4}}}]}
        values={'values':[['id','query','clicks','impressions'],['a','n.a.',0,'n.a.']]}
        with patch('iboomto.storage.request',side_effect=[Mock(json=lambda:meta),Mock(json=lambda:values)]):
            store=Sheets(Mock(),'test')
            self.assertEqual(store.read('GSC Queries'),[{'id':'a','query':'n.a.','clicks':0,'impressions':''}])
            self.assertEqual(store.original['GSC Queries'][1][-1],'n.a.')
