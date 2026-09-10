import unittest,json
from unittest.mock import Mock,patch
from datetime import date,datetime,timezone
from test_monitor import MemoryStore
from iboomto.pages import registry,selected_pages,page_fields
from iboomto.analytics import collect_ga,collect_gsc,collect_business_events,ga_filter
from iboomto.reporting import initialise_config,generate_report,metric_findings
from iboomto.maintenance import maintain,expired
from iboomto.technical import sitemap_collect

class MigrationTests(unittest.TestCase):
    def test_daily_query_ranking_uses_query_only_then_restores_date(self):
        s=MemoryStore();api=Mock()
        def gsc(start,end,dims,*args,**kwargs):
            if dims==['query']:return [{'query':'example','clicks':2,'impressions':20,'ctr':.1,'position':4}],{},False
            if dims==['date']:return [],{'firstIncompleteDate':'2026-09-08'},False
            return [],{},False
        api.gsc.side_effect=gsc
        collect_gsc(api,s,date(2026,9,7),date(2026,9,7),lang='en')
        row=s.read('GSC Queries')[0]
        self.assertEqual((row['query'],row['start'],row['end']),('example','2026-09-07','2026-09-07'))
        self.assertFalse(any(call.args[2]==['date','query'] for call in api.gsc.call_args_list))

    def test_removed_subfolder_does_not_return_to_page_sheets(self):
        from iboomto.collectors import save
        s=MemoryStore()
        for tab in ('GA4 Landing Pages','GSC Pages'):
            save(s,tab,[{'id':'p','subfolder':'tools','page_url':'https://www.iboomto.com/tools'}],lambda r:True,[])
            self.assertNotIn('subfolder',s.read(tab)[0])

    def test_unapproved_ai_evidence_never_leaves_process(self):
        from iboomto.reporting import ai_analyse
        from iboomto.storage import ApiFailure
        with patch.dict('os.environ',{},clear=True),patch('iboomto.reporting.requests.post') as post:
            with self.assertRaises(ApiFailure):ai_analyse({'private_metric':123},MemoryStore())
            post.assert_not_called()

    def test_manual_pages_never_capped_and_deep_english(self):
        s=MemoryStore();s.set('Page name - manual management',[{'Urls':'https://www.iboomto.com/essential-tools/a/b','Lan':'EN','Page Name':'Deep'}, {'Urls':'https://www.iboomto.com/zh-tw','Lan':'TW'}])
        pages=registry(s);chosen=selected_pages(['https://www.iboomto.com/p'+str(i) for i in range(30)],pages,'en')
        self.assertEqual(len(chosen),31)
        fields=page_fields('https://www.iboomto.com/essential-tools/a/b?x=1',pages)
        self.assertEqual((fields['language_path'],fields['subfolder'],fields['page_name']),('en','essential-tools','Deep'))

    def test_exact_host_filter_preserved(self):
        f=ga_filter()['andGroup']['expressions'][0]['filter']
        self.assertEqual(f,{'fieldName':'hostName','stringFilter':{'matchType':'EXACT','value':'www.iboomto.com'}})

    def test_missing_page_rows_are_not_zero(self):
        s=MemoryStore();s.set('Page name - manual management',[{'Urls':'https://www.iboomto.com/essential-tools/a/b','Lan':'EN'}])
        api=Mock();api.ga_timezone.return_value='UTC';api.ga.return_value=([],{})
        collect_ga(api,s,{'id':'123','language':'en'},date(2026,9,7),date(2026,9,8),datetime(2026,9,9,tzinfo=timezone.utc))
        rows=s.read('GA4 Landing Pages');self.assertEqual(len(rows),2)
        self.assertTrue(all(r['data_status']=='no_data_returned' and 'sessions' not in r for r in rows))
        collect_ga(api,s,{'id':'123','language':'en'},date(2026,9,7),date(2026,9,8),datetime(2026,9,9,tzinfo=timezone.utc))
        self.assertEqual(len(s.read('GA4 Landing Pages')),2)

    def test_gsc_camelcase_metadata_and_response_aggregation(self):
        s=MemoryStore();api=Mock()
        def gsc(start,end,dims,lang='all',state='final',*args,**kwargs):
            if dims==['date'] and lang=='all':
                return ([],{},False) if state=='final' else ([{'date':'2026-09-07','clicks':12,'impressions':87,'ctr':12/87,'position':2}],{'firstIncompleteDate':'2026-09-07','responseAggregationType':'byProperty'},False)
            return [],{'responseAggregationType':'byPage'},False
        api.gsc.side_effect=gsc
        r=collect_gsc(api,s,date(2026,9,7),date(2026,9,8))
        self.assertEqual(r['final_through'],'2026-09-06')
        self.assertEqual(r['status'],'waiting_for_final_data')
        self.assertFalse(s.read('GSC Site'))
        self.assertEqual(len(api.gsc.call_args_list),2)

    def test_daily_gsc_caps_all_details_at_confirmed_final_date(self):
        s=MemoryStore();api=Mock()
        s.set('Page name - manual management',[{'Urls':'https://www.iboomto.com/','Lan':'EN'}])
        def gsc(start,end,dims,lang='all',state='final',*args,**kwargs):
            if start<date(2026,9,7):
                return ([{'date':'2026-09-07'}] if state=='final' else []),{'first_incomplete_date':'2026-09-08'},False
            self.assertEqual(state,'final');self.assertLessEqual(end,date(2026,9,7))
            if dims==['date']:return [{'date':'2026-09-07','clicks':2,'impressions':10,'ctr':.2,'position':2}],{'responseAggregationType':'byPage'},False
            return [],{},False
        api.gsc.side_effect=gsc
        result=collect_gsc(api,s,date(2026,9,7),date(2026,9,9),lang='en')
        self.assertEqual(result['collected_end'],'2026-09-07')
        self.assertEqual(result['requested_end'],'2026-09-09')
        self.assertTrue(all(r['quality']=='final' and r['end']=='2026-09-07' for r in s.read('GSC Site')+s.read('GSC Pages')))

    def test_legacy_gsc_preview_never_supersedes_final_in_reports_or_comparisons(self):
        from iboomto.reporting import evidence
        s=MemoryStore();initialise_config(s)
        s.set('GSC Site',[{'id':str(d),'source':'GSC','language':'en','period':'daily','start':f'2026-09-{d:02}','end':f'2026-09-{d:02}',
                          'quality':'final' if d==7 else 'provisional','clicks':d,'impressions':100,'ctr':d/100} for d in (7,8,9)])
        metric_findings(s)
        self.assertTrue(all(r['current_end']=='2026-09-07' for r in s.read('Comparisons')))
        payload=evidence(s,[],[])
        self.assertEqual([r['end'] for r in payload['latest_metrics']],['2026-09-07'])
        self.assertEqual(len(s.read('GSC Site')),3)

    def test_event_period_users_queried_not_summed(self):
        s=MemoryStore();initialise_config(s);s.set('GA4 Site',[{'property':'123','period':'weekly','end':'2026-09-19','totalUsers':10}])
        api=Mock();api.ga_timezone.return_value='UTC';api.ga.return_value=([{'eventCount':8,'totalUsers':4}],{})
        collect_business_events(api,s,{'id':'123','language':'en'},date(2026,9,13),date(2026,9,19),datetime(2026,9,25,tzinfo=timezone.utc),'weekly')
        self.assertEqual(api.ga.call_args.args[3],[])
        self.assertEqual(s.read('GA4 Business Events')[0]['user_conversion_rate'],.4)

    def test_report_views_versions_and_events_input(self):
        s=MemoryStore();report=MemoryStore();initialise_config(s)
        s.set('GA4 Site',[{'id':'x','period':'daily','start':'2026-09-08','end':'2026-09-08','language':'en','quality':'provisional','sessions':20}])
        s.set('GA4 Events',[{'period':'daily','start':'2026-09-08','end':'2026-09-08','language':'en','event_name':'software_download','eventCount':2}])
        answer={'summary':'ok','findings':[],'actions':[],'deep_analysis_candidates':[],'limitations':[]}
        with patch('iboomto.reporting.ai_analyse',return_value=answer) as ai:
            generate_report(s,report,[],[],'1',date(2026,9,9))
            self.assertEqual(ai.call_args.args[0]['detail_summaries']['GA4 Events'][0]['eventCount'],2)
            daily=list(report.read('Overview'))
            generate_report(s,report,[],[],'2',date(2026,9,9),'weekly')
            self.assertEqual(report.read('Overview'),daily);self.assertTrue(report.read('Weekly Overview'))
            s.read('GA4 Site')[0]['sessions']=21
            generate_report(s,report,[],[],'3',date(2026,9,9))
        self.assertEqual(len(report.read('Report History')),3)

    def test_daily_comparison_needs_only_its_baseline(self):
        s=MemoryStore();initialise_config(s)
        s.set('GA4 Site',[{'id':str(i),'period':'daily','start':f'2026-09-{i}','end':f'2026-09-{i}','language':'en','quality':'mature','sessions':n,'activeUsers':n} for i,n in [(13,100),(14,20)]])
        metric_findings(s)
        dod=next(r for r in s.read('Comparisons') if r['comparison']=='day_over_day' and r['metric']=='sessions')
        wow=next(r for r in s.read('Comparisons') if r['comparison']=='same_weekday' and r['metric']=='sessions')
        self.assertEqual(dod['comparison_status'],'comparable');self.assertEqual(wow['comparison_status'],'unavailable')

    def test_unconfigured_archive_never_removes_rows(self):
        s=MemoryStore();s.set('GA4 Events',[{'id':'old','end':'2026-09-07','period':'daily'}])
        result=maintain(s,date(2027,1,1));self.assertEqual(result['status'],'archive_not_configured');self.assertEqual(len(s.read('GA4 Events')),1)

    def test_unchanged_sitemap_does_not_append_full_history(self):
        s=MemoryStore();web=Mock();res=Mock();res.status_code=200;res.content=b'<urlset><url><loc>https://www.iboomto.com/</loc><lastmod>2026-09-07</lastmod></url></urlset>';web.get.return_value=res
        sitemap_collect(s,web);sitemap_collect(s,web)
        self.assertEqual(len(s.read('Sitemap History')),1)

if __name__=='__main__':unittest.main()
