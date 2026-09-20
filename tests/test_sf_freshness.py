import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from test_monitor import MemoryStore
from iboomto.technical import sf_import
from iboomto.reporting import evidence
from iboomto.sf_freshness import fresh_date, fresh_batches

NOW = datetime(2026, 9, 14, 8, tzinfo=timezone.utc)


class SFFreshnessTests(unittest.TestCase):
    def test_dates_fail_closed_and_use_jst(self):
        self.assertTrue(fresh_date('20260914', NOW))
        self.assertTrue(fresh_date('2026-09-13T16:00:00Z', NOW))
        for value in ('20260913', 'unknown', '20260915', ''):
            self.assertFalse(fresh_date(value, NOW))

    def test_old_folder_not_downloaded_or_parsed(self):
        data = MemoryStore()
        with patch('iboomto.technical.drive_list', return_value=[{'id':'old','name':'20260909','mimeType':'application/vnd.google-apps.folder'}]) as listing, patch('iboomto.technical.request') as request, patch('iboomto.technical.parse_csv') as parser:
            issues, status = sf_import(None, data, NOW)
        self.assertEqual(listing.call_count, 1)
        request.assert_not_called()
        parser.assert_not_called()
        self.assertEqual(issues, [])
        self.assertEqual(status['status'], 'skipped_stale')

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
