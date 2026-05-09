"""
monthly_page_ga4.py — Pull GA4 monthly data by page per subdomain.
Same logic as weekly_page_ga4.py but for full calendar month.
Schedule: 4th of month at 4PM JST.
"""

import argparse
import calendar
from datetime import date
from google.analytics.data_v1beta.types import (
    RunReportRequest, Dimension, Metric, DateRange, FilterExpression,
    Filter, FilterExpressionList, OrderBy
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

COL_ALL_USERS_CHANGE = 8
COL_ORG_USERS_CHANGE = 11
COL_ENGAGE = 13
COL_KEY_EVENTS = 15


def get_month_range(ref_date):
    year, month = ref_date.year, ref_date.month
    if month == 1:
        year -= 1; month = 12
    else:
        month -= 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


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


def get_top_pages(ga4, property_id, start, end):
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start.strftime("%Y-%m-%d"), end_date=end.strftime("%Y-%m-%d"))],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="activeUsers")],
        dimension_filter=channel_filter(CHANNEL_ORGANIC_SEARCH),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="activeUsers"), desc=True)],
        limit=TOP_PAGES_COUNT,
    )
    resp = ga4.run_report(req)
    return [row.dimension_values[0].value for row in resp.rows]


def get_page_metrics(ga4, property_id, start, end, page_path, subdomain):
    base_url = f"https://{subdomain}"
    full_url = base_url + page_path if page_path.startswith("/") else page_path
    date_range = DateRange(start_date=start.strftime("%Y-%m-%d"), end_date=end.strftime("%Y-%m-%d"))

    page_filter = FilterExpression(
        filter=Filter(field_name="pagePath",
                      string_filter=Filter.StringFilter(
                          match_type=Filter.StringFilter.MatchType.EXACT,
                          value=page_path)))
    org_page_filter = FilterExpression(
        and_group=FilterExpressionList(
            expressions=[channel_filter(CHANNEL_ORGANIC_SEARCH), page_filter]))

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
            Metric(name="sessions"), Metric(name="activeUsers"),
            Metric(name="newUsers"), Metric(name="engagementRate"),
            Metric(name="averageSessionDuration"), Metric(name="keyEvents"),
        ],
        dimension_filter=org_page_filter,
    )
    resp_org = ga4.run_report(req_org)
    org_s, org_u, new_u, eng_r, avg_d, key_e = 0, 0, 0, 0.0, 0.0, 0
    if resp_org.rows:
        v = resp_org.rows[0].metric_values
        org_s = int(v[0].value); org_u = int(v[1].value); new_u = int(v[2].value)
        eng_r = round(float(v[3].value) * 100, 2)
        avg_d = round(float(v[4].value), 1); key_e = int(v[5].value)

    ctr = round(key_e / org_u, 4) if org_u > 0 else 0
    return {
        "url": full_url, "all_sessions": all_s, "all_users": all_u,
        "org_sessions": org_s, "org_users": org_u, "new_users": new_u,
        "engagement_rate": eng_r, "avg_duration": avg_d,
        "key_events": key_e, "ctr": ctr,
    }


def get_prev_from_sheet(rows, url):
    for row in rows[1:]:
        if len(row) > 5 and row[5] == url:
            def si(idx):
                try: return int(row[idx]) if len(row) > idx else 0
                except: return 0
            def sf(idx):
                try: return float(row[idx]) if len(row) > idx else 0.0
                except: return 0.0
            return {"all_users": si(7), "org_users": si(10),
                    "engagement_rate": sf(13), "key_events": si(15)}
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
    print(f"Running Monthly by Page GA4 for {date_label}")

    ga4 = get_ga4_client()
    sheets = get_sheets_client()
    tab = SHEET_NAMES["monthly_page_ga4"]
    ensure_headers(sheets, tab, HEADERS)

    page_map = read_page_name_map(sheets)
    existing_rows = read_all_rows(sheets, tab)
    all_new_rows = []
    highlight_ops = []

    for prop in PROPERTIES:
        print(f"  Fetching pages for {prop['subdomain']}...")
        pid = prop["ga4"]
        subdomain = prop["subdomain"]
        base_url = f"https://{subdomain}"

        top_paths = get_top_pages(ga4, pid, cur_start, cur_end)
        top_urls = set(base_url + p if p.startswith("/") else p for p in top_paths)
        manual_urls = set(url for url, info in page_map.items()
                         if info["lan"] == prop["lan"] or subdomain in url)
        all_urls = list(top_urls | manual_urls)

        for url in all_urls:
            path = url.replace(base_url, "") or "/"
            metrics = get_page_metrics(ga4, pid, cur_start, cur_end, path, subdomain)
            prev = get_prev_from_sheet(existing_rows, url)
            if prev is None:
                prev_m = get_page_metrics(ga4, pid, prev_start, prev_end, path, subdomain)
                prev = {"all_users": prev_m["all_users"], "org_users": prev_m["org_users"],
                        "engagement_rate": prev_m["engagement_rate"], "key_events": prev_m["key_events"]}

            all_change = metrics["all_users"] - prev["all_users"]
            org_change = metrics["org_users"] - prev["org_users"]
            pinfo = page_map.get(url, {})

            row = [
                date_label, prop["lan"], subdomain,
                pinfo.get("page_type", ""), pinfo.get("page_name", ""), url,
                metrics["all_sessions"], metrics["all_users"], all_change,
                metrics["org_sessions"], metrics["org_users"], org_change,
                metrics["new_users"], metrics["engagement_rate"],
                metrics["avg_duration"], metrics["key_events"], metrics["ctr"],
            ]
            row_index = len(existing_rows) + len(all_new_rows) + 1

            lvl = thresholds.monthly_page_organic_active_users(metrics["org_users"], prev["org_users"])
            if lvl: highlight_ops.append((row_index, COL_ORG_USERS_CHANGE, lvl))

            lvl = thresholds.monthly_page_engagement_ratio(
                metrics["engagement_rate"], prev["engagement_rate"], metrics["org_sessions"])
            if lvl: highlight_ops.append((row_index, COL_ENGAGE, lvl))

            lvl = thresholds.monthly_page_key_events(metrics["key_events"], prev["key_events"])
            if lvl: highlight_ops.append((row_index, COL_KEY_EVENTS, lvl))

            all_new_rows.append(row)

    append_rows(sheets, tab, all_new_rows)
    if highlight_ops:
        batch_highlight(sheets, tab, highlight_ops)
    print(f"Monthly by Page GA4 complete. {len(all_new_rows)} rows written.")


if __name__ == "__main__":
    main()
