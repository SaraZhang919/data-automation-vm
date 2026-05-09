"""
manual_check_gsc.py — Pull GSC data by page for a custom date range.
Same metrics as weekly_page_gsc.py but accepts --start and --end dates.
Writes to "Manual check - GSC" sheet tab (never overwrites automated data).
"""

import argparse
from datetime import date, timedelta
from auth import get_gsc_client, get_sheets_client
from config import PROPERTIES, TOP_PAGES_COUNT
from sheets import ensure_headers, append_rows, read_all_rows, read_page_name_map, batch_highlight
import thresholds

HEADERS = [
    "Date", "Lan", "Subdomain", "Page Type", "Page Name", "Page Url",
    "Clicks", "Clicks Change",
    "Impressions", "Impressions Change",
    "CTR", "CTR Change",
    "Position", "Position Change",
    "Alert"
]

TAB_NAME = "Manual check - GSC"

COL_IMPRESSIONS_CHANGE = 9
COL_POSITION_CHANGE = 13
COL_ALERT = 14


def fetch_gsc_page(gsc, gsc_property, url, start, end):
    body = {
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
        "dimensions": ["page"],
        "dimensionFilterGroups": [{
            "filters": [{
                "dimension": "page",
                "operator": "equals",
                "expression": url
            }]
        }],
        "rowLimit": 1,
    }
    try:
        resp = gsc.searchanalytics().query(siteUrl=gsc_property, body=body).execute()
        rows = resp.get("rows", [])
        if rows:
            r = rows[0]
            return {
                "clicks": int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)),
                "ctr": round(r.get("ctr", 0) * 100, 2),
                "position": round(r.get("position", 0), 1),
            }
    except Exception as e:
        print(f"    GSC error for {url}: {e}")
    return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}


def get_top_pages_gsc(gsc, gsc_property, start, end, limit=TOP_PAGES_COUNT):
    body = {
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
        "dimensions": ["page"],
        "rowLimit": limit,
        "orderBy": [{"fieldName": "clicks", "sortOrder": "DESCENDING"}],
    }
    try:
        resp = gsc.searchanalytics().query(siteUrl=gsc_property, body=body).execute()
        return [r["keys"][0] for r in resp.get("rows", [])]
    except Exception as e:
        print(f"    GSC top pages error: {e}")
        return []


def get_prev_from_sheet(rows, url):
    for row in rows[1:]:
        if len(row) > 5 and row[5] == url:
            def si(idx):
                try: return int(row[idx]) if len(row) > idx else 0
                except: return 0
            def sf(idx):
                try: return float(row[idx]) if len(row) > idx else 0.0
                except: return 0.0
            return {
                "clicks": si(6),
                "impressions": si(8),
                "ctr": sf(10),
                "position": sf(12),
            }
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    args = parser.parse_args()

    cur_start = date.fromisoformat(args.start)
    cur_end = date.fromisoformat(args.end)
    span = (cur_end - cur_start).days + 1
    prev_start = cur_start - timedelta(days=span)
    prev_end = cur_end - timedelta(days=span)
    date_label = f"{cur_start} to {cur_end}"
    print(f"Running Manual Check GSC for {date_label}")

    gsc = get_gsc_client()
    sheets = get_sheets_client()

    tab = TAB_NAME
    ensure_headers(sheets, tab, HEADERS)

    page_map = read_page_name_map(sheets)
    existing_rows = read_all_rows(sheets, tab)

    all_new_rows = []
    highlight_ops = []

    for prop in PROPERTIES:
        print(f"  Fetching GSC pages for {prop['subdomain']}...")
        gsc_prop = prop["gsc"]

        top_urls = set(get_top_pages_gsc(gsc, gsc_prop, cur_start, cur_end))

        manual_urls = set()
        for url, info in page_map.items():
            if info["lan"] == prop["lan"] or prop["subdomain"] in url:
                manual_urls.add(url)

        all_urls = list(top_urls | manual_urls)

        for url in all_urls:
            cur = fetch_gsc_page(gsc, gsc_prop, url, cur_start, cur_end)

            prev = get_prev_from_sheet(existing_rows, url)
            if prev is None:
                prev = fetch_gsc_page(gsc, gsc_prop, url, prev_start, prev_end)

            clicks_change = cur["clicks"] - prev["clicks"]
            imp_change = cur["impressions"] - prev["impressions"]
            ctr_change = round(cur["ctr"] - prev["ctr"], 2)
            pos_change = round(cur["position"] - prev["position"], 1)

            pinfo = page_map.get(url, {})
            page_type = pinfo.get("page_type", "")
            page_name = pinfo.get("page_name", "")

            imp_lvl = thresholds.weekly_page_gsc_impressions(cur["impressions"], prev["impressions"])
            pos_lvl = thresholds.weekly_page_gsc_position(cur["position"], prev["position"])

            combo_alert = ""
            if cur["impressions"] > 1000 and cur["ctr"] < 2.0:
                combo_alert = "High Imp / Low CTR"

            alert = combo_alert
            if imp_lvl == "red" or pos_lvl == "red":
                alert = ("🔴 " + alert).strip()
            elif imp_lvl == "yellow" or pos_lvl == "yellow":
                alert = ("🟡 " + alert).strip()

            row = [
                date_label, prop["lan"], prop["subdomain"],
                page_type, page_name, url,
                cur["clicks"], clicks_change,
                cur["impressions"], imp_change,
                cur["ctr"], ctr_change,
                cur["position"], pos_change,
                alert,
            ]
            row_index = len(existing_rows) + len(all_new_rows) + 1

            if imp_lvl:
                highlight_ops.append((row_index, COL_IMPRESSIONS_CHANGE, imp_lvl))
            if pos_lvl:
                highlight_ops.append((row_index, COL_POSITION_CHANGE, pos_lvl))

            all_new_rows.append(row)

    append_rows(sheets, tab, all_new_rows)
    if highlight_ops:
        batch_highlight(sheets, tab, highlight_ops)

    print(f"Manual Check GSC complete. {len(all_new_rows)} rows written, {len(highlight_ops)} highlights applied.")


if __name__ == "__main__":
    main()
