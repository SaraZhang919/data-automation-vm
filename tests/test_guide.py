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

    def test_clears_legacy_columns_beyond_short_header(self):
        s=self.store()
        with patch.dict('os.environ',{'IBOOMTO_AI_REPORTS_ENABLED':'true'}):update_guide(s)
        with patch('iboomto.storage.request',return_value=Mock(json=lambda:{})) as api:s.flush()
        writes=[call.kwargs['json']['data'] for call in api.call_args_list if call.args[2].endswith('/values:batchUpdate')]
        matrix=[row for batch in writes for block in batch for row in block['values']]
        self.assertTrue(all(len(row)==6 and row[3:]==['','',''] for row in matrix))
        self.assertEqual(matrix[0][:3],['类别','表格或主题','说明'])

    def test_native_name_links_keep_gid_zero_and_no_url_column(self):
        s=self.store()
        with patch.dict('os.environ',{'IBOOMTO_AI_REPORTS_ENABLED':'true'}):update_guide(s)
        rows=s.cache['使用指南 Guide'];links=s.guide_links['使用指南 Guide']
        self.assertTrue(links['Properties'].endswith('#gid=0'))
        self.assertTrue(all(set(row)=={'类别','表格或主题','说明'} for row in rows))
        requests=guide_format_requests(5,rows,links)
        linked=[r['repeatCell'] for r in requests if 'link' in r.get('repeatCell',{}).get('cell',{}).get('userEnteredFormat',{}).get('textFormat',{})]
        self.assertEqual(len(linked),2)
        self.assertTrue(all(r['range']['startColumnIndex']==1 for r in linked))


if __name__=='__main__':unittest.main()
