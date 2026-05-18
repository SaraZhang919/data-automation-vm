"""
weekly_page_ga4.py — Pull GA4 weekly data by page per subdomain.
Pages: Top 30 by organic active users + all URLs in Page name sheet.
Schedule: Every Sunday at 4PM JST.
"""

import argparse
from datetime import date, timedelta
from google.analytics.data_v1beta.types import (
    RunReportRequest, Dimension, Metric, DateRange,
    FilterExpression, Filter, OrderBy
)
from auth import get_ga4_client, get_sheets_client
from config import PROPERTIES, SHEET_NAMES, GA4_CHANNEL_DIM, TOP_PAGES_COUNT
from config import CHANNEL_ORGANIC_SEARCH
from sheets import ensure_headers, append_rows, read_all_rows, read_page_name_map, batch_highlight
import thresholds

HEADERS = [
    "Date", "Lan", "Subdomain", "Page Type", "Page Name", "Page Url",
    "All channel Sessions", "All channel Active Users",
    "All channel Active Users Change Value",
    "Organic Channel sessions", "Organic channel active users",
    "Organic channel active users Change Value",
    "Organic channel new users", "Engagement Ratio",
    "Average session duration", "Key Event Counts", "CTR"
]

# 0-based column indices for data columns we highlight
COL_ALL_USERS_CHANGE = 8
COL_ORG_USERS_CHANGE = 11
COL_ENGAGE = 13
COL_KEY_EVENTS = 15


def get_week_range(ref_date):
    """
    Return (start, end) for the most recent complete Sun–Sat week before ref_date.
    Running on Sunday 2026-05-10 → returns 2026-05-03 to 2026-05-09.
    """
    dow = ref_date.weekday()  # Mon=0 ... Sat=5, Sun=6
    days_back_to_sat = (dow - 5) % 7
    if days_back_to_sat == 0:
        days_back_to_sat = 7
    end = ref_date - timedelta(days=days_back_to_sat)
    start = end - timedelta(days=6)
    return start, end


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


def get_top_pages(ga4, property_id, start, end, limit=TOP_PAGES_COUNT):
    """Get top pages by organic active users."""
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d")
        )],
        dimensions=[Dimension(name="landingPagePlusQueryString")],
        metrics=[Metric(name="activeUsers")],
        dimension_filter=channel_filter(CHANNEL_ORGANIC_SEARCH),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="activeUsers"), desc=True)],
        limit=limit,
    )
    resp = ga4.run_report(req)
    return [row.dimension_values[0].value for row in resp.rows]


def get_page_metrics(ga4, property_id, start, end, page_path, subdomain):
    """Get all required metrics for a specific page."""
    base_url = f"https://{subdomain}"
    full_url = base_url + page_path if page_path.startswith("/") else page_path

    date_range = DateRange(
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d")
    )
    page_filter = FilterExpression(
        filter=Filter(
            field_name="landingPagePlusQueryString",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.CONTAINS,
                value=page_path
            )
        )
    )
    org_page_filter = FilterExpression(
        and_group=FilterExpressionList(
            expressions=[channel_filter(CHANNEL_ORGANIC_SEARCH), page_filter]
        )
    )

    # All channel metrics
    req_all = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[date_range],
        dimensions=[Dimension(name="landingPagePlusQueryString")],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
        dimension_filter=page_filter,
    )
    resp_all = ga4.run_report(req_all)
    all_s, all_u = 0, 0
    if resp_all.rows:
        all_s = int(resp_all.rows[0].metric_values[0].value)
        all_u = int(resp_all.rows[0].metric_values[1].value)

    # Organic metrics
    req_org = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[date_range],
        dimensions=[Dimension(name="landingPagePlusQueryString")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="activeUsers"),
            Metric(name="newUsers"),
            Metric(name="engagementRate"),
            Metric(name="averageSessionDuration"),
            Metric(name="keyEvents"),
        ],
        dimension_filter=org_page_filter,
    )
    resp_org = ga4.run_report(req_org)
    org_s, org_u, new_u, eng_r, avg_d, key_e = 0, 0, 0, 0.0, 0.0, 0
    if resp_org.rows:
        v = resp_org.rows[0].metric_values
        org_s = int(v[0].value)
        org_u = int(v[1].value)
        new_u = int(v[2].value)
        eng_r = round(float(v[3].value) * 100, 2)
        avg_d = round(float(v[4].value), 1)
        key_e = int(v[5].value)

    ctr = round(key_e / org_u, 4) if org_u > 0 else 0

    return {
        "url": full_url,
        "all_sessions": all_s, "all_users": all_u,
        "org_sessions": org_s, "org_users": org_u,
        "new_users": new_u,
        "engagement_rate": eng_r,
        "avg_duration": avg_d,
        "key_events": key_e,
        "ctr": ctr,
    }


def get_prev_metrics_from_sheet(rows, url):
    """Look up previous week's metrics for a URL from existing sheet data."""
    for row in rows[1:]:
        if len(row) > 5 and row[5] == url:
            def si(idx): 
                try: return int(row[idx]) if len(row) > idx else 0
                except: return 0
            def sf(idx):
                try: return float(row[idx]) if len(row) > idx else 0.0
                except: return 0.0
            return {
                "all_users": si(7),
                "org_users": si(10),
                "org_sessions": si(9),   # col 9 = Organic Channel sessions
                "engagement_rate": sf(13),
                "key_events": si(15),
            }
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Reference Sunday YYYY-MM-DD")
    args = parser.parse_args()

    ref = date.fromisoformat(args.date) if args.date else date.today()
    cur_start, cur_end = get_week_range(ref)
    prev_start = cur_start - timedelta(days=7)
    prev_end = cur_end - timedelta(days=7)
    date_label = f"{cur_start} to {cur_end}"
    print(f"Running Weekly by Page GA4 for {date_label}")

    ga4 = get_ga4_client()
    sheets = get_sheets_client()
    tab = SHEET_NAMES["weekly_page_ga4"]
    ensure_headers(sheets, tab, HEADERS)

    page_map = read_page_name_map(sheets)
    existing_row_count = len(read_all_rows(sheets, tab))  # for row_index offset only

    all_new_rows = []
    highlight_ops = []

    for prop in PROPERTIES:
        print(f"  Fetching pages for {prop['subdomain']}...")
        pid = prop["ga4"]
        subdomain = prop["subdomain"]
        base_url = f"https://{subdomain}"

        # Get top organic pages
        top_paths = get_top_pages(ga4, pid, cur_start, cur_end)
        top_urls = set()
        for p in top_paths:
            top_urls.add(base_url + p if p.startswith("/") else p)

        # Add Page name sheet URLs for this lan
        manual_urls = set()
        for url, info in page_map.items():
            if info["lan"] == prop["lan"] or subdomain in url:
                manual_urls.add(url)

        all_urls = list(top_urls | manual_urls)

        for url in all_urls:
            path = url.replace(base_url, "") or "/"
            metrics = get_page_metrics(ga4, pid, cur_start, cur_end, path, subdomain)

            # Get previous values
            # Always fetch prev from API for accurate comparison
            prev_m = get_page_metrics(ga4, pid, prev_start, prev_end, path, subdomain)
            prev = {
                "all_users": prev_m["all_users"],
                "org_users": prev_m["org_users"],
                "org_sessions": prev_m["org_sessions"],
                "engagement_rate": prev_m["engagement_rate"],
                "key_events": prev_m["key_events"],
            }

            all_change = metrics["all_users"] - prev["all_users"]
            org_change = metrics["org_users"] - prev["org_users"]

            # Page name lookup
            pinfo = page_map.get(url, {})
            page_type = pinfo.get("page_type", "")
            page_name = pinfo.get("page_name", "")

            row = [
                date_label, prop["lan"], subdomain,
                page_type, page_name, url,
                metrics["all_sessions"], metrics["all_users"], all_change,
                metrics["org_sessions"], metrics["org_users"], org_change,
                metrics["new_users"], metrics["engagement_rate"],
                metrics["avg_duration"], metrics["key_events"], metrics["ctr"],
            ]
            row_index = existing_row_count + len(all_new_rows) + 1

            # Threshold checks
            lvl = thresholds.weekly_page_all_channel_active_users(metrics["all_users"], prev["all_users"])
            if lvl: highlight_ops.append((row_index, COL_ALL_USERS_CHANGE, lvl))

            lvl = thresholds.weekly_page_organic_active_users_page(metrics["org_users"], prev["org_users"])
            if lvl: highlight_ops.append((row_index, COL_ORG_USERS_CHANGE, lvl))

            lvl = thresholds.weekly_page_engagement_ratio(
                metrics["engagement_rate"], prev["engagement_rate"],
                prev["org_sessions"]
            )
            if lvl: highlight_ops.append((row_index, COL_ENGAGE, lvl))

            lvl = thresholds.weekly_page_key_events(metrics["key_events"], prev["key_events"])
            if lvl: highlight_ops.append((row_index, COL_KEY_EVENTS, lvl))

            all_new_rows.append(row)

    append_rows(sheets, tab, all_new_rows)
    if highlight_ops:
        batch_highlight(sheets, tab, highlight_ops)

    print(f"Weekly by Page GA4 complete. {len(all_new_rows)} rows written, {len(highlight_ops)} highlights applied.")


if __name__ == "__main__":
    from google.analytics.data_v1beta.types import FilterExpressionList
    main()
