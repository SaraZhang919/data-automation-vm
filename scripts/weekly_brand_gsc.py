"""
weekly_brand_gsc.py — Pull GSC brand query data per subdomain.
Filters: exact "Vidmud" + queries containing "vidmud".
Schedule: Every Tuesday at 4PM JST.
"""

import argparse
from datetime import date, timedelta
from auth import get_gsc_client, get_sheets_client
from config import PROPERTIES, SHEET_NAMES, BRAND_EXACT, BRAND_CONTAINS
from sheets import ensure_headers, append_rows, read_all_rows, batch_highlight
import thresholds

HEADERS = [
    "Date", "Lan", "Subdomain", "Query",
    "Impressions", "Impressions Change",
    "CTR", "CTR Change",
    "Position", "Position Change",
]

COL_IMP_CHANGE = 5
COL_CTR_CHANGE = 7
COL_POS_CHANGE = 9


def get_week_range(ref_date):
    """
    Return (start, end) for the most recent complete Sun–Sat week before ref_date.
    Tuesday 2026-05-12 → 2026-05-03 to 2026-05-09.
    """
    dow = ref_date.weekday()  # Mon=0 ... Sat=5, Sun=6
    days_back_to_sat = (dow - 5) % 7
    if days_back_to_sat == 0:
        days_back_to_sat = 7
    end = ref_date - timedelta(days=days_back_to_sat)
    start = end - timedelta(days=6)
    return start, end


def fetch_brand_queries(gsc, gsc_property, start, end):
    """Fetch all brand queries (exact + contains Vidmud)."""
    body = {
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
        "dimensions": ["query"],
        "rowLimit": 1000,
    }
    try:
        resp = gsc.searchanalytics().query(siteUrl=gsc_property, body=body).execute()
        rows = resp.get("rows", [])
        results = []
        for r in rows:
            query = r["keys"][0]
            if query.lower() == BRAND_EXACT.lower() or BRAND_CONTAINS.lower() in query.lower():
                results.append({
                    "query": query,
                    "impressions": int(r.get("impressions", 0)),
                    "ctr": round(r.get("ctr", 0) * 100, 2),
                    "position": round(r.get("position", 0), 1),
                    "clicks": int(r.get("clicks", 0)),
                })
        return results
    except Exception as e:
        print(f"    Brand query error: {e}")
        return []


def get_prev_from_sheet(rows, subdomain, query):
    """Get previous metrics for a subdomain+query from sheet."""
    for row in rows[1:]:
        if len(row) > 3 and row[2] == subdomain and row[3] == query:
            def si(idx):
                try: return int(row[idx]) if len(row) > idx else 0
                except: return 0
            def sf(idx):
                try: return float(row[idx]) if len(row) > idx else 0.0
                except: return 0.0
            return {
                "impressions": si(4),
                "ctr": sf(6),
                "position": sf(8),
                "clicks": si(4),  # clicks not in headers but used for threshold
            }
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Reference Tuesday YYYY-MM-DD")
    args = parser.parse_args()

    ref = date.fromisoformat(args.date) if args.date else date.today()
    cur_start, cur_end = get_week_range(ref)
    prev_start = cur_start - timedelta(days=7)
    prev_end = cur_end - timedelta(days=7)
    date_label = f"{cur_start} to {cur_end}"
    print(f"Running Weekly Brand GSC for {date_label}")

    gsc = get_gsc_client()
    sheets = get_sheets_client()
    tab = SHEET_NAMES["weekly_brand"]
    ensure_headers(sheets, tab, HEADERS)

    existing_row_count = len(read_all_rows(sheets, tab))  # for row_index offset only
    all_new_rows = []
    highlight_ops = []

    for prop in PROPERTIES:
        print(f"  Fetching brand queries for {prop['subdomain']}...")
        cur_queries = fetch_brand_queries(gsc, prop["gsc"], cur_start, cur_end)

        for q in cur_queries:
            # Always fetch prev from API for accurate comparison
            prev_queries = fetch_brand_queries(gsc, prop["gsc"], prev_start, prev_end)
            prev_match = next((p for p in prev_queries if p["query"] == q["query"]), None)
            prev = prev_match if prev_match else {
                "impressions": 0, "ctr": 0.0, "position": 0.0, "clicks": 0
            }

            imp_change = q["impressions"] - prev["impressions"]
            ctr_change = round(q["ctr"] - prev["ctr"], 2)
            pos_change = round(q["position"] - prev["position"], 1)

            row = [
                date_label, prop["lan"], prop["subdomain"], q["query"],
                q["impressions"], imp_change,
                q["ctr"], ctr_change,
                q["position"], pos_change,
            ]
            row_index = existing_row_count + len(all_new_rows) + 1

            lvl = thresholds.weekly_brand_clicks(q["clicks"], prev["clicks"])
            if lvl:
                highlight_ops.append((row_index, COL_IMP_CHANGE, lvl))

            all_new_rows.append(row)

    append_rows(sheets, tab, all_new_rows)
    if highlight_ops:
        batch_highlight(sheets, tab, highlight_ops)

    print(f"Weekly Brand GSC complete. {len(all_new_rows)} rows written.")


if __name__ == "__main__":
    main()
