"""
daily_site_gsc.py — Pull GSC daily site-level data per subdomain.
Fetches data for 3 days ago (GSC delay). No comparison or highlighting.
Schedule: Every day at 4PM JST.
"""

import argparse
from datetime import date, timedelta
from auth import get_gsc_client, get_sheets_client
from config import PROPERTIES, SHEET_NAMES
from sheets import ensure_headers, append_rows

HEADERS = [
    "Date", "Lan", "Subdomain",
    "Clicks", "Impressions", "CTR", "Position",
]


def fetch_gsc_site(gsc, gsc_property, target_date):
    """Fetch site-level GSC totals for a single day."""
    d = target_date.strftime("%Y-%m-%d")
    body = {
        "startDate": d,
        "endDate":   d,
        "dimensions": [],
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
    parser.add_argument("--date", help="Reference date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    ref = date.fromisoformat(args.date.replace("/", "-")) if args.date else date.today()
    target_date = ref - timedelta(days=3)  # GSC delay: fetch 3 days ago
    print(f"Running Daily Site GSC for {target_date}")

    gsc    = get_gsc_client()
    sheets = get_sheets_client()
    tab    = SHEET_NAMES["daily_site_gsc"]
    ensure_headers(sheets, tab, HEADERS)

    rows = []
    for prop in PROPERTIES:
        print(f"  Fetching {prop['subdomain']}...")
        data = fetch_gsc_site(gsc, prop["gsc"], target_date)
        row = [
            target_date.isoformat(), prop["lan"], prop["subdomain"],
            data["clicks"], data["impressions"], data["ctr"], data["position"],
        ]
        rows.append(row)

    append_rows(sheets, tab, rows)
    print(f"Daily Site GSC complete. {len(rows)} rows written.")


if __name__ == "__main__":
    main()
