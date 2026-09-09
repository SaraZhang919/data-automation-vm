import unittest
from datetime import date,datetime,timezone
from unittest.mock import Mock
from iboomto.core import language,daily_window,previous_week,previous_month,mature,count_alert,parse_properties
from iboomto.storage import Sheets
from iboomto.analytics import collect_ga,collect_gsc
from iboomto.technical import parse_csv,sitemap_collect
from iboomto.reporting import reconcile_issues

class MemoryStore(Sheets):
    def __init__(self):
        self.cache={};self.headers={};self.dirty=set();self.old_sizes={};self.tabs={};self.write=False
    def read(self,name):return self.cache.setdefault(name,[])
    def set(self,name,rows,headers=None):self.cache[name]=rows

class CoreTests(unittest.TestCase):
    def test_language_boundaries(self):
        for u in ['/essential-tools','/essential-tools/a/b','/essential-tools/es/example','/esoteric']:
            self.assertEqual(language('https://www.iboomto.com'+u),'en')
        for u in ['/es','/es/','/es/a/b']:
            self.assertEqual(language(u),'es')
        self.assertEqual(language('/pt/pdf-para-md'),'pt')
        self.assertEqual(language('/zh-tw'),'zh-tw')
        self.assertEqual(language('/x?language=ar'),'en')
        self.assertIsNone(language('https://evil.example/es'))
        self.assertIsNone(language('/installer.exe'))

    def test_calendar_not_runner_timezone(self):
        now=datetime(2026,9,15,8,tzinfo=timezone.utc)
        self.assertEqual(daily_window(now,'America/Los_Angeles'),(date(2026,9,8),date(2026,9,14)))
        now=datetime(2026,9,15,1,tzinfo=timezone.utc)
        self.assertEqual(daily_window(now,'America/Los_Angeles')[1],date(2026,9,13))
        self.assertEqual(previous_week(date(2026,9,15)),(date(2026,9,6),date(2026,9,12)))
        self.assertEqual(previous_month(date(2027,1,4)),(date(2026,12,1),date(2026,12,31)))
        self.assertFalse(mature(date(2026,9,13),'America/Los_Angeles',datetime(2026,9,15,8,tzinfo=timezone.utc)))

    def test_small_samples_and_absolute_gates(self):
        self.assertEqual(count_alert(0,10),'observe')
        self.assertEqual(count_alert(0,60),'red')
        self.assertEqual(count_alert(90,100),'normal')
        self.assertEqual(count_alert(5,0),'new_signal')
        self.assertEqual(count_alert(0,60,'impressions'),'observe')

    def test_upsert_does_not_duplicate(self):
        s=MemoryStore();s.upsert('x',[{'id':'one','value':1}]);s.upsert('x',[{'id':'one','value':2}])
        self.assertEqual(s.read('x'),[{'id':'one','value':2}])

    def test_whole_period_users_not_daily_sum(self):
        s=MemoryStore();api=Mock();api.ga_timezone.return_value='America/Los_Angeles'
        def ga(pid,start,end,dims,metrics,filters):
            self.assertEqual(start,date(2026,9,13));self.assertEqual(end,date(2026,9,19));self.assertNotIn('date',dims)
            row={k:5 for k in metrics};row.update({k:'sample' for k in dims});row['totalUsers']=5
            return [row],{}
        api.ga.side_effect=ga
        collect_ga(api,s,{'id':'123','language':'en'},date(2026,9,13),date(2026,9,19),datetime(2026,9,25,tzinfo=timezone.utc),'weekly')
        self.assertEqual(s.read('GA4 Weekly Daily')[0]['totalUsers'],5)

    def test_failed_query_keeps_previous_data(self):
        s=MemoryStore();s.set('GA4 Daily',[{'id':'old','sessions':100}]);api=Mock();api.ga_timezone.return_value='UTC';api.ga.side_effect=RuntimeError('down')
        with self.assertRaises(RuntimeError):collect_ga(api,s,{'id':'123','language':'en'},date(2026,9,7),date(2026,9,8),datetime(2026,9,10,tzinfo=timezone.utc))
        self.assertEqual(s.read('GA4 Daily')[0]['sessions'],100)

    def test_csv_headers_and_malformed_rows(self):
        self.assertEqual(parse_csv(b'From,To\na,b\n',['From','To'])[0]['From'],'a')
        with self.assertRaises(Exception):parse_csv(b'From,To\na,b,c\n',['From','To'])

    def test_sitemap_partial_preserves_old_urls(self):
        s=MemoryStore();s.set('Sitemap URLs',[{'id':'old','url':'https://www.iboomto.com/old'}]);web=Mock();web.get.side_effect=RuntimeError('down')
        urls,complete=sitemap_collect(s,web)
        self.assertFalse(complete);self.assertEqual(s.read('Sitemap URLs')[0]['id'],'old')

    def test_issue_resolution_requires_successful_fresh_check(self):
        s=MemoryStore();s.set('Issues',[{'id':'a','url':'u','source':'Technical Checks','state':'persistent'}])
        self.assertEqual(reconcile_issues(s,[],set())[0]['state'],'persistent')
        self.assertEqual(reconcile_issues(s,[],{'u'})[0]['state'],'resolved')

if __name__=='__main__':unittest.main()
