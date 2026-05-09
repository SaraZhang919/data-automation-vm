"""
manual_page_detail_gsc.py — Pull GSC data for a specific page name across all subdomains.
Shows daily breakdown per URL.
Accepts --start, --end, --page_name, and optional --url_filter.
Writes to "Manual page detail - GSC" sheet tab.
"""

import argparse
from datetime import date, timedelta
from auth import get_gsc_client, get_sheets_client
from config import PROPERTIES
from sheets import ensure_headers, append_rows, read_page_name_map
import thresholds

TAB_NAME = "Manual page detail - GSC"

HEADERS = [
    "Row Type",       # "Daily"
    "Date",
    "Lan", "Subdomain", "Page Type", "Page Name", "Page Url",
    "Clicks", "Impressions", "CTR %", "Position",
    "Alert"
]


# ---------------------------------------------------------------------------
# GSC helpers
# ---------------------------------------------------------------------------

def fetch_gsc_daily(gsc, gsc_property: str, url: str, start: date, end: date):
    """
    Return list of dicts, one per day, with GSC metrics for a specific URL.
    """
    body = {
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate":   end.strftime("%Y-%m-%d"),
        "dimensions": ["date", "page"],
        "dimensionFilterGroups": [{
            "filters": [{
                "dimension": "page",
                "operator":  "equals",
                "expression": url
            }]
        }],
        "rowLimit": 25000,
    }
    try:
        resp = gsc.searchanalytics().query(siteUrl=gsc_property, body=body).execute()
        rows = resp.get("rows", [])
    except Exception as e:
        print(f"    GSC error for {url}: {e}")
        rows = []

    # Index by date
    by_date = {}
    for row in rows:
        d = row["keys"][0]   # YYYY-MM-DD
        by_date[d] = {
            "clicks":      int(row.get("clicks", 0)),
            "impressions": int(row.get("impressions", 0)),
            "ctr":         round(row.get("ctr", 0) * 100, 2),
            "position":    round(row.get("position", 0), 1),
        }

    # Build a row for every day in range (fill zeros for missing days)
    results = []
    current = start
    while current <= end:
        d_key = current.isoformat()
        day   = by_date.get(d_key, {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0})

        # Alert logic per day
        combo_alert = ""
        if day["impressions"] > 1000 and day["ctr"] < 2.0:
            combo_alert = "High Imp / Low CTR"

        results.append({
            "date": d_key,
            **day,
            "alert": combo_alert,
        })
        current += timedelta(days=1)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",      required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end",        required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--page_name",  required=True, help="Page name to filter (e.g. Home)")
    parser.add_argument("--url_filter", default="",    help="Optional: narrow to one specific URL")
    args = parser.parse_args()

    cur_start = date.fromisoformat(args.start)
    cur_end   = date.fromisoformat(args.end)
    page_name_filter = args.page_name.strip().lower()
    url_filter = args.url_filter.strip()

    print(f"Running Manual Page Detail GSC | {cur_start} to {cur_end} | page: '{args.page_name}'"
          + (f" | url: {url_filter}" if url_filter else ""))

    gsc    = get_gsc_client()
    sheets = get_sheets_client()

    ensure_headers(sheets, TAB_NAME, HEADERS)

    # Build URL list from page name map
    page_map = read_page_name_map(sheets)
    matched_urls = {}   # url -> {page_type, page_name, lan, subdomain, gsc_property}

    for url, info in page_map.items():
        if info["page_name"].strip().lower() != page_name_filter:
            continue
        if url_filter and url != url_filter:
            continue
        for prop in PROPERTIES:
            if prop["lan"] == info["lan"] or prop["subdomain"] in url:
                matched_urls[url] = {
                    "page_type":    info["page_type"],
                    "page_name":    info["page_name"],
                    "lan":          prop["lan"],
                    "subdomain":    prop["subdomain"],
                    "gsc_property": prop["gsc"],
                }
                break

    if not matched_urls:
        print(f"No URLs found for page name '{args.page_name}'"
              + (f" and url '{url_filter}'" if url_filter else "")
              + ". Check the 'Page name - manual management' sheet.")
        return

    print(f"Found {len(matched_urls)} URL(s) matching '{args.page_name}'")

    all_new_rows = []

    for url, info in matched_urls.items():
        print(f"  [{info['lan']}] Fetching daily GSC data for {url} …")
        daily = fetch_gsc_daily(gsc, info["gsc_property"], url, cur_start, cur_end)

        for day in daily:
            row = [
                "Daily",
                day["date"],
                info["lan"], info["subdomain"],
                info["page_type"], info["page_name"], url,
                day["clicks"], day["impressions"], day["ctr"], day["position"],
                day["alert"],
            ]
            all_new_rows.append(row)

    append_rows(sheets, TAB_NAME, all_new_rows)
    print(f"Manual Page Detail GSC complete. {len(all_new_rows)} rows written.")


if __name__ == "__main__":
    main()
