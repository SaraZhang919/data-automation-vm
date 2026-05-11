"""
manual_page_detail_ga4.py — Pull GA4 data for a specific page name across all subdomains.
Shows daily breakdown per URL.
Accepts --start, --end, --page_name, and optional --url_filter.
Both --page_name and --url_filter support pipe-separated values (OR logic).
  e.g. --page_name "Home|Online Tool"  --url_filter "/home|/tool"
Writes to "Manual page detail - GA4" sheet tab.
"""

import argparse
from datetime import date, timedelta
from google.analytics.data_v1beta.types import (
    RunReportRequest, Dimension, Metric, DateRange,
    FilterExpression, Filter, FilterExpressionList, OrderBy
)
from auth import get_ga4_client, get_sheets_client
from config import PROPERTIES, GA4_CHANNEL_DIM, CHANNEL_ORGANIC_SEARCH
from sheets import ensure_headers, append_rows, read_page_name_map, batch_highlight
import thresholds

TAB_NAME = "Manual page detail - GA4"

HEADERS = [
    "Row Type",       # "Daily"
    "Date",
    "Lan", "Subdomain", "Page Type", "Page Name", "Page Url",
    "All channel Sessions", "All channel Active Users",
    "Organic Sessions", "Organic Active Users",
    "New Users", "Engagement Rate %",
    "Avg Session Duration", "Key Events", "CTR"
]

COL_ORG_USERS   = 10   # 0-based for highlight
COL_KEY_EVENTS  = 14
COL_ENGAGE      = 12


# ---------------------------------------------------------------------------
# GA4 helpers
# ---------------------------------------------------------------------------

def channel_filter(channel_value):
    return FilterExpression(
        filter=Filter(
            field_name=GA4_CHANNEL_DIM,
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value=channel_value
            )
        )
    )


def get_daily_metrics(ga4, property_id, start: date, end: date, page_path: str, subdomain: str):
    """
    Return a list of dicts, one per day from start to end, with GA4 metrics.
    """
    date_range = DateRange(
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d")
    )
    page_filter = FilterExpression(
        filter=Filter(
            field_name="pagePath",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value=page_path
            )
        )
    )
    org_page_filter = FilterExpression(
        and_group=FilterExpressionList(
            expressions=[channel_filter(CHANNEL_ORGANIC_SEARCH), page_filter]
        )
    )

    # All channel — daily
    req_all = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[date_range],
        dimensions=[Dimension(name="date"), Dimension(name="pagePath")],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
        dimension_filter=page_filter,
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
    )
    resp_all = ga4.run_report(req_all)
    all_by_date = {}
    for row in resp_all.rows:
        d = row.dimension_values[0].value  # YYYYMMDD
        all_by_date[d] = {
            "all_sessions": int(row.metric_values[0].value),
            "all_users":    int(row.metric_values[1].value),
        }

    # Organic — daily
    req_org = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[date_range],
        dimensions=[Dimension(name="date"), Dimension(name="pagePath")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="activeUsers"),
            Metric(name="newUsers"),
            Metric(name="engagementRate"),
            Metric(name="averageSessionDuration"),
            Metric(name="keyEvents"),
        ],
        dimension_filter=org_page_filter,
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
    )
    resp_org = ga4.run_report(req_org)
    org_by_date = {}
    for row in resp_org.rows:
        d = row.dimension_values[0].value
        v = row.metric_values
        org_by_date[d] = {
            "org_sessions":    int(v[0].value),
            "org_users":       int(v[1].value),
            "new_users":       int(v[2].value),
            "engagement_rate": round(float(v[3].value) * 100, 2),
            "avg_duration":    round(float(v[4].value), 1),
            "key_events":      int(v[5].value),
        }

    # Build daily rows for every day in range
    results = []
    current = start
    while current <= end:
        d_key = current.strftime("%Y%m%d")
        a = all_by_date.get(d_key, {"all_sessions": 0, "all_users": 0})
        o = org_by_date.get(d_key, {
            "org_sessions": 0, "org_users": 0, "new_users": 0,
            "engagement_rate": 0.0, "avg_duration": 0.0, "key_events": 0
        })
        ctr = round(o["key_events"] / o["org_users"], 4) if o["org_users"] > 0 else 0
        results.append({
            "date": current.isoformat(),
            **a, **o, "ctr": ctr
        })
        current += timedelta(days=1)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",       required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end",         required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--page_name",   required=True, help="Page name to filter (e.g. Home)")
    parser.add_argument("--url_filter",  default="",    help="Optional: narrow to one specific URL")
    args = parser.parse_args()

    cur_start = date.fromisoformat(args.start)
    cur_end   = date.fromisoformat(args.end)

    # Support pipe-separated values for both filters (OR logic)
    page_name_filters = [v.strip().lower() for v in args.page_name.split("|") if v.strip()]
    url_filters       = [v.strip() for v in args.url_filter.split("|") if v.strip()]

    print(f"Running Manual Page Detail GA4 | {cur_start} to {cur_end} | page: '{args.page_name}'"
          + (f" | url: {args.url_filter}" if url_filters else ""))

    ga4    = get_ga4_client()
    sheets = get_sheets_client()

    ensure_headers(sheets, TAB_NAME, HEADERS)

    # Build URL list from page name map
    page_map = read_page_name_map(sheets)
    matched_urls = {}   # url -> {page_type, page_name, lan, subdomain, ga4_id}

    for url, info in page_map.items():
        if info["page_name"].strip().lower() not in page_name_filters:
            continue
        if url_filters and not any(f in url for f in url_filters):
            continue
        # Find matching property
        for prop in PROPERTIES:
            if prop["lan"] == info["lan"] or prop["subdomain"] in url:
                matched_urls[url] = {
                    "page_type": info["page_type"],
                    "page_name": info["page_name"],
                    "lan":       prop["lan"],
                    "subdomain": prop["subdomain"],
                    "ga4_id":    prop["ga4"],
                }
                break

    if not matched_urls:
        print(f"No URLs found for page name '{args.page_name}'"
              + (f" and url filter '{args.url_filter}'" if url_filters else "")
              + ". Check the 'Page name - manual management' sheet.")
        return

    print(f"Found {len(matched_urls)} URL(s) matching '{args.page_name}'")

    all_new_rows = []

    for url, info in matched_urls.items():
        subdomain = info["subdomain"]
        base_url  = f"https://{subdomain}"
        path      = url.replace(base_url, "") or "/"
        pid       = info["ga4_id"]

        print(f"  [{info['lan']}] Fetching daily data for {url} …")
        daily = get_daily_metrics(ga4, pid, cur_start, cur_end, path, subdomain)

        for day in daily:
            row = [
                "Daily",
                day["date"],
                info["lan"], subdomain, info["page_type"], info["page_name"], url,
                day["all_sessions"], day["all_users"],
                day["org_sessions"], day["org_users"],
                day["new_users"], day["engagement_rate"],
                day["avg_duration"], day["key_events"], day["ctr"],
            ]
            all_new_rows.append(row)

    append_rows(sheets, TAB_NAME, all_new_rows)
    print(f"Manual Page Detail GA4 complete. {len(all_new_rows)} rows written.")


if __name__ == "__main__":
    main()
