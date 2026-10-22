import unittest
from unittest.mock import Mock, patch

from iboomto.storage import Sheets, inherited_formats


class FilteredFormattingTests(unittest.TestCase):
    def test_growing_filtered_sheet_repeats_formats_without_copying_rows(self):
        store = Sheets.__new__(Sheets)
        store.s = Mock()
        store.base = 'https://sheets.googleapis.com/v4/spreadsheets/test'
        store.write = True
        name = 'Event Check Summary'
        store.tabs = {name: {'sheetId': 123, 'gridProperties': {'rowCount': 100, 'columnCount': 26}}}
        store.headers = {name: ['event_name', 'eventCount', 'id']}
        store.original = {name: [['event_name', 'eventCount', 'id'], ['hidden_by_filter', 10, 'old']]}
        store.old_sizes = {name: 2}
        store.cache = {name: [{'event_name': 'hidden_by_filter', 'eventCount': 10, 'id': 'old'},
                              {'event_name': 'new_event', 'eventCount': 20, 'id': 'new'}]}
        store.dirty = {name}
        count_format = {'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0'}}

        def respond(session, method, url, **kwargs):
            if method == 'GET':
                return Mock(json=lambda: {'sheets': [{'data': [{'rowData': [{'values': [
                    {}, {'userEnteredFormat': count_format}, {}]}]}]}]})
            return Mock(json=lambda: {})

        with patch('iboomto.storage.request', side_effect=respond) as request:
            store.flush()
        read = next(call for call in request.call_args_list if call.args[1] == 'GET')
        self.assertEqual(read.kwargs['params']['ranges'], "'Event Check Summary'!A2:C2")
        edits = [edit for call in request.call_args_list
                 for edit in call.kwargs.get('json', {}).get('requests', [])]
        self.assertFalse(any('copyPaste' in edit or 'clearBasicFilter' in edit or 'setBasicFilter' in edit for edit in edits))
        repeat = [edit['repeatCell'] for edit in edits if 'repeatCell' in edit]
        numeric = next(edit for edit in repeat if edit['range']['startColumnIndex'] == 1)
        self.assertEqual(numeric['cell']['userEnteredFormat'], count_format)
        self.assertEqual(numeric['range'], {'sheetId': 123, 'startRowIndex': 2, 'endRowIndex': 3,
                                           'startColumnIndex': 1, 'endColumnIndex': 2})
        self.assertEqual(numeric['fields'], 'userEnteredFormat')
        self.assertFalse(store.dirty)

    def test_default_formats_group_adjacent_columns_and_escape_tab_names(self):
        with patch('iboomto.storage.request', return_value=Mock(json=lambda: {'sheets': [{'data': []}]})) as request:
            edits = inherited_formats(Mock(), 'url', "Owner's report", 9, 20, 25, 3)
        self.assertEqual(request.call_args.kwargs['params']['ranges'], "'Owner''s report'!A21:C21")
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]['repeatCell']['range']['startRowIndex'], 21)
        self.assertEqual(edits[0]['repeatCell']['range']['endRowIndex'], 25)
        self.assertEqual(edits[0]['repeatCell']['range']['endColumnIndex'], 3)
        self.assertEqual(edits[0]['repeatCell']['cell'], {'userEnteredFormat': {}})


if __name__ == '__main__':
    unittest.main()
