import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, call, patch
from test_monitor import MemoryStore
from iboomto.technical import sf_import
from iboomto.reporting import evidence, reconcile_issues
from iboomto.sf_freshness import fresh_date, fresh_batches
from iboomto.issue_freshness import retire_stale

NOW = datetime(2026, 9, 14, 8, tzinfo=timezone.utc)
NAMES = ('internal_all.csv', 'inlinks.csv', 'hreflang_all.csv')


def folder(day):
    return {'id':day,'name':day,'mimeType':'application/vnd.google-apps.folder'}


def files():
    return [{'id':name,'name':name,'md5Checksum':name,'modifiedTime':'2026-09-13T07:00:00Z'} for name in NAMES]


class SFFreshnessTests(unittest.TestCase):
    def test_dates_fail_closed_and_use_jst(self):
        self.assertTrue(fresh_date('20260914', NOW))
        self.assertTrue(fresh_date('2026-09-13T16:00:00Z', NOW))
        for value in ('20260913', 'unknown', '20260915', ''):
            self.assertFalse(fresh_date(value, NOW))

    def test_folders_older_than_the_saved_crawl_and_future_folders_are_not_downloaded(self):
        data = MemoryStore()
        data.set('Import Batches',[{'id':'saved','status':'success','batch_date':'20260912','crawl_timestamp':'2026-09-12 15:00:00','freshness_policy':'same-jst-day-v1'}])
        with patch('iboomto.technical.drive_list', return_value=[folder('20260909'),folder('20260915')]) as listing, patch('iboomto.technical.request') as request:
            issues, status = sf_import(None, data, NOW)
        self.assertEqual(listing.call_count, 1)
        request.assert_not_called()
        self.assertEqual(issues, [])
        self.assertEqual(status['status'], 'skipped_stale')
        self.assertEqual(status['latest_batch'], '20260912')

    def test_newest_complete_batch_catches_up_and_ages_from_crawl_day(self):
        data = MemoryStore()
        url = 'https://www.iboomto.com/a'
        csvs = {
            NAMES[0]:f'Address,Status Code,Content Type,Crawl Timestamp\n{url},500,text/html,2026-09-13 12:00:00\n',
            NAMES[1]:'From,To\n',
            NAMES[2]:'Address\n',
        }
        def download(_session, _method, url, **_kwargs):
            return Mock(content=csvs[url.rsplit('/',1)[-1]].encode())
        with patch('iboomto.technical.drive_list', side_effect=[
            [folder('20260912'),folder('20260913'),folder('20260914')],
            files()[:2],files(),files(),
        ]) as listing, patch('iboomto.technical.request',side_effect=download):
            issues, status = sf_import(None, data, NOW)
        self.assertEqual(listing.call_args_list[1:], [call(None,'20260914'),call(None,'20260913'),call(None,'20260913')])
        self.assertEqual((status['imported'],status['latest_crawl_date'],status['status']), (1,'2026-09-13','success'))
        self.assertEqual(issues[0]['evidence']['crawl_timestamp'],'2026-09-13T12:00:00+09:00')
        latest, = fresh_batches(data, NOW)
        self.assertEqual(data.read('SF Pages')[0]['batch'],latest['id'])
        self.assertEqual(retire_stale([{**issues[0],'state':'new'}],data,NOW)[0]['state'],'new')
        self.assertEqual(retire_stale([{**issues[0],'state':'new'}],data,NOW+timedelta(days=1))[0]['state'],'historical')

    def test_stale_and_legacy_batches_excluded(self):
        data = MemoryStore()
        data.set('Import Batches', [
            {'id':'old','status':'success','crawl_timestamp':'20260913','freshness_policy':'same-jst-day-v1'},
            {'id':'legacy','status':'success','crawl_timestamp':'20260914'},
            {'id':'fresh','status':'success','crawl_timestamp':'20260914','freshness_policy':'same-jst-day-v1'}])
        self.assertEqual([r['id'] for r in fresh_batches(data, NOW)], ['fresh'])

    def test_old_crawl_in_today_folder_never_updates_snapshot(self):
        from unittest.mock import Mock
        data=MemoryStore()
        data.set('SF Pages',[{'id':'keep','url':'https://www.iboomto.com/keep'}])
        folder={'id':'folder','name':'20260914','mimeType':'application/vnd.google-apps.folder'}
        names=['internal_all.csv','inlinks.csv','hreflang_all.csv']
        files=[{'id':n,'name':n,'md5Checksum':n,'modifiedTime':'2026-09-14T06:00:00Z'} for n in names]
        pages=[{'Address':'https://www.iboomto.com/a','Status Code':'500','Content Type':'text/html','Crawl Timestamp':'2026-09-09 12:00:00'}]
        with patch('iboomto.technical.drive_list',side_effect=[[folder],files,files]), patch('iboomto.technical.request',return_value=Mock(content=b'csv')), patch('iboomto.technical.parse_csv',side_effect=[pages,[],[]]):
            findings,status=sf_import(None,data,NOW)
        self.assertEqual(findings,[])
        self.assertEqual(data.read('SF Pages')[0]['id'],'keep')
        self.assertEqual(data.read('Import Batches')[0]['status'],'skipped_stale')

    def test_same_batch_is_not_downloaded_twice(self):
        from iboomto.core import digest
        data=MemoryStore()
        folder={'id':'folder','name':'20260914','mimeType':'application/vnd.google-apps.folder'}
        names=['internal_all.csv','inlinks.csv','hreflang_all.csv']
        files=[{'id':n,'name':n,'md5Checksum':n,'modifiedTime':'2026-09-14T06:00:00Z'} for n in names]
        bid=digest(['folder',[(n,n,'2026-09-14T06:00:00Z') for n in names]])
        data.set('Import Batches',[{'id':bid,'status':'success','schema_version':'compact-v2','batch_date':'20260914','crawl_timestamp':'20260914','freshness_policy':'same-jst-day-v1'}])
        with patch('iboomto.technical.drive_list',side_effect=[[folder],files]), patch('iboomto.technical.request') as request:
            _,status=sf_import(None,data,NOW)
        request.assert_not_called()
        self.assertEqual(status['imported'],0)

    def test_all_report_types_exclude_old_sf_issues_and_batches(self):
        data = MemoryStore()
        data.set('Import Batches',[{'id':'old','status':'success','batch_date':'20260909'}])
        from iboomto.core import stamp
        observed=stamp()
        data.set('Technical Checks',[{'url':'https://www.iboomto.com/a','checked_at':observed,'check_status':'success'}])
        issues=[{'source':'SF Pages','kind':'sf_http_error','evidence':{'batch':'old'}},
                {'source':'SF Pages','kind':'no_internal_inlink_in_export'},
                {'source':'Technical Checks','kind':'http_error','url':'https://www.iboomto.com/a','observed_at':observed}]
        for kind in ('daily','weekly','weekly-preview','monthly'):
            payload=evidence(data,[{'source':'Screaming Frog','latest_batch':'20260909'}],issues,kind)
            self.assertEqual(payload['sf_batches'],[])
            self.assertEqual([r['source'] for r in payload['issues']],['Technical Checks'])
            self.assertNotIn('20260909',str(payload))

    def test_fresh_batch_matches_issue_provenance(self):
        from iboomto.sf_freshness import report_issue_allowed
        batches=[{'id':'new'}]
        self.assertTrue(report_issue_allowed({'source':'SF Pages','sf_batch':'new'},batches))
        self.assertTrue(report_issue_allowed({'kind':'sf_http_error','evidence':'{"batch":"new"}'},batches))
        self.assertFalse(report_issue_allowed({'source':'SF Pages','sf_batch':'old'},batches))

    def test_revised_export_of_same_crawl_updates_issue_provenance(self):
        report = MemoryStore()
        row = {'id':'x','kind':'sf_http_error','url':'https://www.iboomto.com/a','source':'SF Pages',
               'last_seen':'2026-09-13 12:00:00','state':'persistent','severity':'yellow',
               'evidence':'{"batch":"previous"}'}
        report.set('Issues', [row])
        finding = {**row,'observed_at':'2026-09-13T12:00:00+09:00','evidence':{'batch':'revised'}}
        updated, = reconcile_issues(report,[finding],[])
        self.assertEqual(updated['evidence']['batch'],'revised')
