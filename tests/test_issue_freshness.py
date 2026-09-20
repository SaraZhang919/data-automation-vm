import unittest
from datetime import datetime, timezone
from test_monitor import MemoryStore
from iboomto.issue_freshness import retire_stale, current_issue
from iboomto.llm_evidence import compact_evidence

NOW=datetime(2026,9,20,8,tzinfo=timezone.utc)
class IssueFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.store=MemoryStore()
        self.old={'id':'x','source':'Technical Checks','url':'https://www.iboomto.com/store','kind':'http_error','state':'persistent','observed_at':'2026-09-13T13:00:00Z','last_seen':'2026-09-13T13:00:00Z'}
    def test_removed_candidate_is_historical_not_resolved(self):
        self.store.set('Sitemap Sources',[{'status':'success','checked_at':NOW.isoformat()}])
        row=retire_stale([dict(self.old)],self.store,NOW)[0]
        self.assertEqual(row['state'],'historical');self.assertEqual(row['last_seen'],self.old['last_seen'])
        self.assertFalse(current_issue(row,self.store,NOW))
    def test_incomplete_inventory_or_still_registered_requires_recheck(self):
        self.assertEqual(retire_stale([dict(self.old)],self.store,NOW)[0]['state'],'needs_recheck')
        self.store.set('Sitemap Sources',[{'status':'success','checked_at':NOW.isoformat()}])
        self.store.set('Page name - manual management',[{'Urls':self.old['url']}])
        self.assertEqual(retire_stale([dict(self.old)],self.store,NOW)[0]['state'],'needs_recheck')
    def test_fresh_verified_error_survives_but_old_error_never_does(self):
        row={**self.old,'observed_at':NOW.isoformat()}
        self.store.set('Technical Checks',[{'url':row['url'],'checked_at':NOW.isoformat(),'check_status':'success'}])
        self.assertTrue(current_issue(row,self.store,NOW))
        self.assertFalse(current_issue(self.old,self.store,NOW))
        self.assertFalse(current_issue({**row,'observed_at':'' ,'last_seen':''},self.store,NOW))
    def test_stale_sf_retires_without_claiming_fixed(self):
        row={**self.old,'source':'SF Pages','kind':'sf_http_error','evidence':{'batch':'old'}}
        self.assertEqual(retire_stale([row],self.store,NOW)[0]['state'],'historical')
    def test_compact_payload_preserves_evidence_dates(self):
        data=compact_evidence({'issues':[self.old]})['issues']
        self.assertEqual(data['common']['evidence_observed_at'],self.old['observed_at'])
        self.assertEqual(data['common']['evidence_last_seen'],self.old['last_seen'])
