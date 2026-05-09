"""
sheets.py — Google Sheets helpers: read, write, highlight, and header management.
"""

import os
from auth import get_sheets_client
from config import COLOR_YELLOW, COLOR_RED, COLOR_NONE

SHEET_ID = os.environ.get("SHEET_ID")


def get_sheet_tab_id(sheets, tab_name):
    """Return the numeric sheetId for a named tab."""
    meta = sheets.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    raise ValueError(f"Tab '{tab_name}' not found in spreadsheet.")


def ensure_headers(sheets, tab_name, headers):
    """Write header row if row 1 is empty."""
    result = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"'{tab_name}'!1:1"
    ).execute()
    existing = result.get("values", [[]])
    if not existing or not existing[0]:
        sheets.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f"'{tab_name}'!A1",
            valueInputOption="RAW",
            body={"values": [headers]}
        ).execute()


def append_rows(sheets, tab_name, rows):
    """Append rows to a sheet tab."""
    if not rows:
        return
    sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows}
    ).execute()


def read_all_rows(sheets, tab_name):
    """Read all rows from a sheet tab. Returns list of lists."""
    result = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"'{tab_name}'!A:ZZ"
    ).execute()
    return result.get("values", [])


def read_column(sheets, tab_name, col_letter):
    """Read a single column from a sheet tab."""
    result = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"'{tab_name}'!{col_letter}:{col_letter}"
    ).execute()
    return [r[0] if r else "" for r in result.get("values", [])]


def highlight_cell(sheets, tab_name, row_index, col_index, level):
    """
    Highlight a cell by alert level.
    row_index and col_index are 0-based.
    level: 'yellow', 'red', or None (clear)
    """
    tab_id = get_sheet_tab_id(sheets, tab_name)
    if level == "yellow":
        color = COLOR_YELLOW
    elif level == "red":
        color = COLOR_RED
    else:
        color = COLOR_NONE

    body = {
        "requests": [{
            "repeatCell": {
                "range": {
                    "sheetId": tab_id,
                    "startRowIndex": row_index,
                    "endRowIndex": row_index + 1,
                    "startColumnIndex": col_index,
                    "endColumnIndex": col_index + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": color
                    }
                },
                "fields": "userEnteredFormat.backgroundColor"
            }
        }]
    }
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID, body=body
    ).execute()


def batch_highlight(sheets, tab_name, highlights):
    """
    Apply multiple highlights in one API call.
    highlights: list of (row_index, col_index, level) tuples — all 0-based.
    """
    if not highlights:
        return
    tab_id = get_sheet_tab_id(sheets, tab_name)
    requests = []
    for row_index, col_index, level in highlights:
        if level == "yellow":
            color = COLOR_YELLOW
        elif level == "red":
            color = COLOR_RED
        else:
            color = COLOR_NONE
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": tab_id,
                    "startRowIndex": row_index,
                    "endRowIndex": row_index + 1,
                    "startColumnIndex": col_index,
                    "endColumnIndex": col_index + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": color
                    }
                },
                "fields": "userEnteredFormat.backgroundColor"
            }
        })
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID, body={"requests": requests}
    ).execute()


def read_page_name_map(sheets):
    """
    Read the Page name - manual management sheet.
    Returns dict: {url: {"page_type": ..., "page_name": ..., "lan": ...}}
    Expected columns: Page Type, Page Name, Lan, Urls
    """
    from config import SHEET_NAMES
    rows = read_all_rows(sheets, SHEET_NAMES["page_names"])
    if len(rows) < 2:
        return {}
    headers = [h.strip().lower() for h in rows[0]]
    mapping = {}
    for row in rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        d = dict(zip(headers, padded))
        url = d.get("urls", "").strip()
        if url:
            mapping[url] = {
                "page_type": d.get("page type", ""),
                "page_name": d.get("page name", ""),
                "lan": d.get("lan", ""),
            }
    return mapping
