import unittest
from unittest.mock import Mock, patch
from iboomto.storage import Sheets
from iboomto.guide import update_guide, guide_format_requests


class GuideTests(unittest.TestCase):
    def store(self):
        s=Sheets.__new__(Sheets)
        s.s=Mock();s.id='data';s.base='https://sheets.googleapis.com/v4/spreadsheets/data';s.write=True
        s.tabs={'使用指南 Guide':{'sheetId':5,'gridProperties':{'rowCount':100,'columnCount':6}},
                'Properties':{'sheetId':0},'GA4 Site':{'sheetId':8}}
        s.cache={'使用指南 Guide':[{'类别':'old'}]};s.headers={'使用指南 Guide':['类别']}
        s.original={'使用指南 Guide':[['类别'],['old','','','','stale E','stale F']]}
        s.old_sizes={'使用指南 Guide':2};s.dirty=set()
        return s

    def test_routine_job_never_rewrites_existing_guide(self):
        s=self.store()
        before=__import__('copy').deepcopy(s.original)
        with patch.dict('os.environ',{'IBOOMTO_AI_REPORTS_ENABLED':'true'}):update_guide(s)
        with patch('iboomto.storage.request',return_value=Mock(json=lambda:{})) as api:s.flush()
        api.assert_not_called();self.assertEqual(s.original,before)
        with self.assertRaises(ValueError):s.set('使用指南 Guide',[{'说明':'overwrite'}])

    def test_existing_column_order_and_layout_are_preserved(self):
        s=self.store();name='GA4 Site'
        s.tabs[name]={'sheetId':8,'hidden':True,'gridProperties':{'rowCount':100,'columnCount':8}}
        s.cache[name]=[{'sessions':12,'period':'daily','id':'a'}];s.headers[name]=['sessions','period','id']
        s.original[name]=[['sessions','period','id'],[12,'daily','a']];s.old_sizes[name]=2
        s.set(name,[{'period':'daily','id':'a','sessions':15}],headers=['id','period','sessions'])
        with patch('iboomto.storage.request',return_value=Mock(json=lambda:{})) as api:s.flush()
        writes=[c.kwargs['json']['data'] for c in api.call_args_list if c.args[2].endswith('/values:batchUpdate')]
        self.assertEqual(writes[0][0]['values'],[[15,'daily','a']])
        edits=[r for c in api.call_args_list for r in c.kwargs.get('json',{}).get('requests',[])]
        self.assertTrue(all(set(r)=={'updateSheetProperties'} and r['updateSheetProperties']['fields']=='gridProperties.rowCount,gridProperties.columnCount' for r in edits))

    def test_native_name_links_keep_gid_zero_and_no_url_column(self):
        s=self.store()
        s.tabs.pop('使用指南 Guide');s.cache.clear();s.headers.clear();s.original.clear();s.old_sizes.clear()
        with patch.dict('os.environ',{'IBOOMTO_AI_REPORTS_ENABLED':'true'}):update_guide(s)
        rows=s.cache['Guide'];links=s.guide_links['Guide']
        self.assertTrue(links['Properties'].endswith('#gid=0'))
        self.assertTrue(all(set(row)=={'类别','表格或主题','说明'} for row in rows))
        requests=guide_format_requests(5,rows,links)
        linked=[r['repeatCell'] for r in requests if 'link' in r.get('repeatCell',{}).get('cell',{}).get('userEnteredFormat',{}).get('textFormat',{})]
        self.assertEqual(len(linked),2)
        self.assertTrue(all(r['range']['startColumnIndex']==1 for r in linked))


if __name__=='__main__':unittest.main()
