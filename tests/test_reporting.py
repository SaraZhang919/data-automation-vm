import unittest
from unittest.mock import patch,Mock
from datetime import date
from test_monitor import MemoryStore
from iboomto.reporting import generate_report,initialise_config,metric_findings
from iboomto.storage import Sheets

class ReportingTests(unittest.TestCase):
    def test_ai_failure_still_produces_facts(self):
        data=MemoryStore();report=MemoryStore();initialise_config(data)
        data.set('GA4 Daily',[{'id':'a','language':'en','end':'2026-09-08','quality':'provisional','sessions':50}])
        with patch('iboomto.reporting.ai_analyse',side_effect=RuntimeError('API unavailable')):
            result=generate_report(data,report,[],[],'run',date(2026,9,9))
        self.assertEqual(result['status'],'failed')
        self.assertTrue(any(r['section']=='GA4 Daily' for r in report.read('Overview')))

    def test_issued_report_does_not_call_llm_on_backfill(self):
        data=MemoryStore();report=MemoryStore();initialise_config(data)
        answer={'summary':'ok','findings':[],'actions':[],'deep_analysis_candidates':[],'limitations':[]}
        with patch('iboomto.reporting.ai_analyse',return_value=answer) as ai:
            generate_report(data,report,[],[],'first',date(2026,9,9))
            generate_report(data,report,[],[],'second',date(2026,9,9))
            self.assertEqual(ai.call_count,1)
        self.assertEqual(len(report.read('Daily History')),1)

    def test_provisional_drop_is_not_an_alert(self):
        data=MemoryStore();initialise_config(data)
        data.set('GA4 Daily',[{'id':str(i),'end':f'2026-09-{i:02}','language':'en','quality':'provisional','sessions':0,'activeUsers':0} for i in range(7,16)])
        self.assertEqual(metric_findings(data),[])

    def test_sheets_flush_batches_multiple_tabs_and_raw_values(self):
        s=Sheets.__new__(Sheets)
        s.write=True;s.base='https://sheets.googleapis.com/v4/spreadsheets/test';s.s=Mock()
        s.cache={'A':[{'id':'x','text':'=not_a_formula'}],'B':[{'id':'y','count':2}]}
        s.headers={'A':['id','text'],'B':['id','count']};s.old_sizes={'A':0,'B':0};s.dirty={'A','B'};s.tabs={}
        first=Mock();first.json.return_value={'replies':[{'addSheet':{'properties':{'title':'A','sheetId':1}}},{'addSheet':{'properties':{'title':'B','sheetId':2}}}]}
        with patch('iboomto.storage.request',side_effect=[first,Mock(),Mock()]) as req:
            s.flush()
            self.assertEqual(req.call_count,3)
            body=req.call_args_list[1].kwargs['json']
            self.assertEqual(body['valueInputOption'],'RAW')
            self.assertEqual(len(body['data']),2)
            self.assertEqual(body['data'][0]['values'][1][1],'=not_a_formula')
        self.assertFalse(s.dirty)

if __name__=='__main__':unittest.main()
