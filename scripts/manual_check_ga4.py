"""
manual_check_ga4.py — Pull GA4 data by page for a custom date range.
Same metrics as weekly_page_ga4.py but accepts --start and --end dates.
Optionally filter by pipe-separated page names or URL substrings.
  --page_names "homepage|onlinetool"   matches Page Name column (case-insensitive)
  --url_filter "/home|/tool"           matches URL substring (case-insensitive)
  Both filters use OR logic. If neither is set, all pages are included.
Writes to "Manual check - GA4" sheet tab (never overwrites automated data).
"""

import argparse
from datetime import date, timedelta
from google.analytics.data_v1beta.types import (
    RunReportRequest, Dimension, Metric, DateRange,
    FilterExpression, Filter, FilterExpressionList, OrderBy
)
from auth import get_ga4_client, get_sheets_client
from config import PROPERTIES, GA4_CHANNEL_DIM, TOP_PAGES_COUNT
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

TAB_NAME = "Manual check - GA4"

COL_ALL_USERS_CHANGE = 8
COL_ORG_USERS_CHANGE = 11
COL_ENGAGE = 13
COL_KEY_EVENTS = 15


def parse_pipe(value):
    """Split pipe-separated input into a list of stripped lowercase values. Empty → []."""
    if not value:
        return []
    return [v.strip().lower() for v in value.split("|") if v.strip()]


def url_matches_filters(url, page_name, page_name_filters, url_filters):
    """
    Return True if this URL/page should be included.
    - No filters set → include everything.
    - page_name_filters → page_name must match one (case-insensitive).
    - url_filters → URL must contain one of the substrings (case-insensitive).
    - Both set → either match qualifies (OR logic).
    """
    if not page_name_filters and not url_filters:
        return True
    if page_name_filters and page_name.lower() in page_name_filters:
        return True
    if url_filters and any(f in url.lower() for f in url_filters):
        return True
    return False


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
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d")
        )],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="activeUsers")],
        dimension_filter=channel_filter(CHANNEL_ORGANIC_SEARCH),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="activeUsers"), desc=True)],
        limit=limit,
    )
    resp = ga4.run_report(req)
    return [row.dimension_values[0].value for row in resp.rows]


def get_page_metrics(ga4, property_id, start, end, page_path, subdomain):
    base_url = f"https://{subdomain}"
    full_url = base_url + page_path if page_path.startswith("/") else page_path

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

    req_all = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[date_range],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
        dimension_filter=page_filter,
    )
    resp_all = ga4.run_report(req_all)
    all_s, all_u = 0, 0
    if resp_all.rows:
        all_s = int(resp_all.rows[0].metric_values[0].value)
        all_u = int(resp_all.rows[0].metric_values[1].value)

    req_org = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[date_range],
        dimensions=[Dimension(name="pagePath")],
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
                "engagement_rate": sf(13),
                "key_events": si(15),
            }
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--page_names", default="",
                        help="Pipe-separated page names, e.g. homepage|onlinetool")
    parser.add_argument("--url_filter", default="",
                        help="Pipe-separated URL substrings, e.g. /home|/tool")
    args = parser.parse_args()

    page_name_filters = parse_pipe(args.page_names)
    url_filters       = parse_pipe(args.url_filter)

    filter_desc = ""
    if page_name_filters: filter_desc += f" | pages: {page_name_filters}"
    if url_filters:       filter_desc += f" | urls: {url_filters}"

    cur_start  = date.fromisoformat(args.start)
    cur_end    = date.fromisoformat(args.end)
    span       = (cur_end - cur_start).days + 1
    prev_start = cur_start - timedelta(days=span)
    prev_end   = cur_end   - timedelta(days=span)
    date_label = f"{cur_start} to {cur_end}"
    print(f"Running Manual Check GA4 for {date_label}{filter_desc}")

    ga4    = get_ga4_client()
    sheets = get_sheets_client()

    tab = TAB_NAME
    ensure_headers(sheets, tab, HEADERS)

    page_map      = read_page_name_map(sheets)
    existing_rows = read_all_rows(sheets, tab)

    all_new_rows  = []
    highlight_ops = []

    for prop in PROPERTIES:
        print(f"  Fetching pages for {prop['subdomain']}...")
        pid       = prop["ga4"]
        subdomain = prop["subdomain"]
        base_url  = f"https://{subdomain}"

        # Only hit the API for top-30 when no filter is active (saves quota)
        top_urls = set()
        if not page_name_filters and not url_filters:
            top_paths = get_top_pages(ga4, pid, cur_start, cur_end)
            for p in top_paths:
                top_urls.add(base_url + p if p.startswith("/") else p)

        # URLs from the Page name sheet for this subdomain
        manual_urls = set()
        for url, info in page_map.items():
            if info["lan"] == prop["lan"] or subdomain in url:
                manual_urls.add(url)

        all_urls = list(top_urls | manual_urls)

        # Apply filters
        filtered_urls = []
        for url in all_urls:
            pinfo = page_map.get(url, {})
            pname = pinfo.get("page_name", "")
            if url_matches_filters(url, pname, page_name_filters, url_filters):
                filtered_urls.append(url)

        if not filtered_urls:
            print(f"    No matching pages — skipping.")
            continue

        for url in filtered_urls:
            path    = url.replace(base_url, "") or "/"
            metrics = get_page_metrics(ga4, pid, cur_start, cur_end, path, subdomain)

            prev = get_prev_metrics_from_sheet(existing_rows, url)
            if prev is None:
                prev_m = get_page_metrics(ga4, pid, prev_start, prev_end, path, subdomain)
                prev = {
                    "all_users":       prev_m["all_users"],
                    "org_users":       prev_m["org_users"],
                    "engagement_rate": prev_m["engagement_rate"],
                    "key_events":      prev_m["key_events"],
                }

            all_change = metrics["all_users"] - prev["all_users"]
            org_change = metrics["org_users"] - prev["org_users"]

            pinfo     = page_map.get(url, {})
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
            row_index = len(existing_rows) + len(all_new_rows) + 1

            lvl = thresholds.weekly_page_all_channel_active_users(metrics["all_users"], prev["all_users"])
            if lvl: highlight_ops.append((row_index, COL_ALL_USERS_CHANGE, lvl))

            lvl = thresholds.weekly_page_organic_active_users_page(metrics["org_users"], prev["org_users"])
            if lvl: highlight_ops.append((row_index, COL_ORG_USERS_CHANGE, lvl))

            lvl = thresholds.weekly_page_engagement_ratio(
                metrics["engagement_rate"], prev["engagement_rate"], metrics["org_sessions"]
            )
            if lvl: highlight_ops.append((row_index, COL_ENGAGE, lvl))

            lvl = thresholds.weekly_page_key_events(metrics["key_events"], prev["key_events"])
            if lvl: highlight_ops.append((row_index, COL_KEY_EVENTS, lvl))

            all_new_rows.append(row)

    append_rows(sheets, tab, all_new_rows)
    if highlight_ops:
        batch_highlight(sheets, tab, highlight_ops)

    print(f"Manual Check GA4 complete. {len(all_new_rows)} rows written, {len(highlight_ops)} highlights applied.")


if __name__ == "__main__":
    main()
