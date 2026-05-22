"""
weekly_site_gsc.py — Pull GSC weekly site-level data per subdomain.
Date range: The completed Sun–Sat week before the reference date.
Schedule: Every Tuesday at 4PM JST.
"""

import argparse
from datetime import date, timedelta
from auth import get_gsc_client, get_sheets_client
from config import PROPERTIES, SHEET_NAMES
from sheets import ensure_headers, append_rows, read_all_rows, batch_highlight
import thresholds

HEADERS = [
    "Date", "Lan", "Subdomain",
    "Clicks", "Clicks Change",
    "Impressions", "Impressions Change",
    "CTR", "CTR Change",
    "Position", "Position Change",
]

COL_CLICKS_CHANGE      = 4
COL_IMPRESSIONS_CHANGE = 6


def get_week_range(ref_date):
    dow = ref_date.weekday()
    days_back_to_sat = (dow - 5) % 7
    if days_back_to_sat == 0:
        days_back_to_sat = 7
    end = ref_date - timedelta(days=days_back_to_sat)
    start = end - timedelta(days=6)
    return start, end


def fetch_gsc_site(gsc, gsc_property, start, end):
    """Fetch site-level GSC totals — no page dimension."""
    body = {
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate":   end.strftime("%Y-%m-%d"),
        "dimensions": [],   # NO dimension = true site-level aggregate
    }
    try:
        resp = gsc.searchanalytics().query(siteUrl=gsc_property, body=body).execute()
        rows = resp.get("rows", [])
        if rows:
            r = rows[0]
            return {
                "clicks":      int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)),
                "ctr":         round(r.get("ctr", 0) * 100, 2),
                "position":    round(r.get("position", 0), 1),
            }
    except Exception as e:
        print(f"    GSC site error: {e}")
    return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Reference Tuesday YYYY-MM-DD")
    args = parser.parse_args()

    ref = date.fromisoformat(args.date.replace("/", "-")) if args.date else date.today()
    cur_start, cur_end = get_week_range(ref)
    prev_start = cur_start - timedelta(days=7)
    prev_end   = cur_end   - timedelta(days=7)
    date_label = f"{cur_start} to {cur_end}"
    print(f"Running Weekly Site GSC for {date_label}")

    gsc    = get_gsc_client()
    sheets = get_sheets_client()
    tab    = SHEET_NAMES["weekly_site_gsc"]
    ensure_headers(sheets, tab, HEADERS)

    existing_row_count = len(read_all_rows(sheets, tab))
    all_new_rows  = []
    highlight_ops = []

    for prop in PROPERTIES:
        print(f"  Fetching {prop['subdomain']}...")
        cur  = fetch_gsc_site(gsc, prop["gsc"], cur_start, cur_end)
        prev = fetch_gsc_site(gsc, prop["gsc"], prev_start, prev_end)

        clicks_change = cur["clicks"]      - prev["clicks"]
        imp_change    = cur["impressions"] - prev["impressions"]
        ctr_change    = round(cur["ctr"]   - prev["ctr"], 2)
        pos_change    = round(cur["position"] - prev["position"], 1)

        row = [
            date_label, prop["lan"], prop["subdomain"],
            cur["clicks"],      clicks_change,
            cur["impressions"], imp_change,
            cur["ctr"],         ctr_change,
            cur["position"],    pos_change,
        ]

        row_index = existing_row_count + len(all_new_rows) + 1

        lvl = thresholds.weekly_site_gsc_clicks(cur["clicks"], prev["clicks"])
        if lvl: highlight_ops.append((row_index, COL_CLICKS_CHANGE, lvl))

        lvl = thresholds.weekly_site_gsc_impressions(cur["impressions"], prev["impressions"])
        if lvl: highlight_ops.append((row_index, COL_IMPRESSIONS_CHANGE, lvl))

        all_new_rows.append(row)

    append_rows(sheets, tab, all_new_rows)
    if highlight_ops:
        batch_highlight(sheets, tab, highlight_ops)
    print(f"Weekly Site GSC complete. {len(all_new_rows)} rows written, {len(highlight_ops)} highlights applied.")


if __name__ == "__main__":
    main()
