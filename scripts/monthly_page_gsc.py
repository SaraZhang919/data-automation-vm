"""
monthly_page_gsc.py — Pull GSC monthly data by page per subdomain.
Same logic as weekly_page_gsc.py but for full calendar month.
Schedule: 4th of month at 4PM JST.
"""

import argparse
import calendar
from datetime import date
from auth import get_gsc_client, get_sheets_client
from config import PROPERTIES, SHEET_NAMES, TOP_PAGES_COUNT
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

COL_IMP_CHANGE = 9
COL_POS_CHANGE = 13


def get_month_range(ref_date):
    year, month = ref_date.year, ref_date.month
    if month == 1:
        year -= 1; month = 12
    else:
        month -= 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def get_top_pages_gsc(gsc, gsc_property, start, end):
    body = {
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
        "dimensions": ["page"],
        "rowLimit": TOP_PAGES_COUNT,
        "orderBy": [{"fieldName": "clicks", "sortOrder": "DESCENDING"}],
    }
    try:
        resp = gsc.searchanalytics().query(siteUrl=gsc_property, body=body).execute()
        return [r["keys"][0] for r in resp.get("rows", [])]
    except Exception as e:
        print(f"    GSC top pages error: {e}")
        return []


def fetch_gsc_page(gsc, gsc_property, url, start, end):
    body = {
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
        "dimensions": ["page"],
        "dimensionFilterGroups": [{"filters": [{"dimension": "page", "operator": "equals", "expression": url}]}],
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
        print(f"    GSC page error for {url}: {e}")
    return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}


def get_prev_from_sheet(rows, url):
    for row in rows[1:]:
        if len(row) > 5 and row[5] == url:
            def si(idx):
                try: return int(row[idx]) if len(row) > idx else 0
                except: return 0
            def sf(idx):
                try: return float(row[idx]) if len(row) > idx else 0.0
                except: return 0.0
            return {"clicks": si(6), "impressions": si(8), "ctr": sf(10), "position": sf(12)}
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Reference date YYYY-MM-DD")
    args = parser.parse_args()

    ref = date.fromisoformat(args.date) if args.date else date.today()
    cur_start, cur_end = get_month_range(ref)
    prev_ref = date(cur_start.year, cur_start.month, 1) - __import__('datetime').timedelta(days=1)
    prev_start, prev_end = get_month_range(prev_ref)
    date_label = f"{cur_start} to {cur_end}"
    print(f"Running Monthly by Page GSC for {date_label}")

    gsc = get_gsc_client()
    sheets = get_sheets_client()
    tab = SHEET_NAMES["monthly_page_gsc"]
    ensure_headers(sheets, tab, HEADERS)

    page_map = read_page_name_map(sheets)
    existing_row_count = len(read_all_rows(sheets, tab))  # for row_index offset only
    all_new_rows = []
    highlight_ops = []

    for prop in PROPERTIES:
        print(f"  Fetching GSC pages for {prop['subdomain']}...")
        # Filter to only URLs belonging to this subdomain (sc-domain: returns all subdomains)
        top_urls = set(
            url for url in get_top_pages_gsc(gsc, prop["gsc"], cur_start, cur_end)
            if prop["subdomain"] in url
        )
        manual_urls = set(url for url, info in page_map.items()
                         if prop["subdomain"] in url)
        all_urls = list(top_urls | manual_urls)

        for url in all_urls:
            cur = fetch_gsc_page(gsc, prop["gsc"], url, cur_start, cur_end)
            # Always fetch prev from API for accurate comparison
            prev = fetch_gsc_page(gsc, prop["gsc"], url, prev_start, prev_end)

            clicks_change = cur["clicks"] - prev["clicks"]
            imp_change = cur["impressions"] - prev["impressions"]
            ctr_change = round(cur["ctr"] - prev["ctr"], 2)
            pos_change = round(cur["position"] - prev["position"], 1)

            pinfo = page_map.get(url, {})
            imp_lvl = thresholds.monthly_page_gsc_impressions(cur["impressions"], prev["impressions"])
            pos_lvl = thresholds.monthly_page_gsc_position(cur["position"], prev["position"])

            combo_alert = "High Imp / Low CTR" if cur["impressions"] > 3000 and cur["ctr"] < 2.0 else ""
            alert = combo_alert
            if imp_lvl == "red" or pos_lvl == "red":
                alert = ("🔴 " + alert).strip()
            elif imp_lvl == "yellow" or pos_lvl == "yellow":
                alert = ("🟡 " + alert).strip()

            row = [
                date_label, prop["lan"], prop["subdomain"],
                pinfo.get("page_type", ""), pinfo.get("page_name", ""), url,
                cur["clicks"], clicks_change,
                cur["impressions"], imp_change,
                cur["ctr"], ctr_change,
                cur["position"], pos_change,
                alert,
            ]
            row_index = existing_row_count + len(all_new_rows) + 1

            if imp_lvl: highlight_ops.append((row_index, COL_IMP_CHANGE, imp_lvl))
            if pos_lvl: highlight_ops.append((row_index, COL_POS_CHANGE, pos_lvl))

            all_new_rows.append(row)

    append_rows(sheets, tab, all_new_rows)
    if highlight_ops:
        batch_highlight(sheets, tab, highlight_ops)
    print(f"Monthly by Page GSC complete. {len(all_new_rows)} rows written.")


if __name__ == "__main__":
    main()
