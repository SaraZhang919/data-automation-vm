"""
monthly_site_ga4.py — Pull GA4 monthly site-level data per subdomain.
Date range: 1st to last day of previous month.
Schedule: 4th of month at 4PM JST.
Includes DAU/MAU stickiness metric.
"""

import argparse
from datetime import date, timedelta
import calendar
from google.analytics.data_v1beta.types import (
    RunReportRequest, Dimension, Metric, DateRange, FilterExpression, Filter
)
from auth import get_ga4_client, get_sheets_client
from config import PROPERTIES, SHEET_NAMES, GA4_CHANNEL_DIM
from config import CHANNEL_ORGANIC_SEARCH, CHANNEL_DIRECT, CHANNEL_REFERRAL
from config import CHANNEL_ORGANIC_SOCIAL, CHANNEL_PAID_SEARCH
from sheets import ensure_headers, append_rows, read_all_rows

HEADERS = [
    "Date", "Lan", "Subdomain",
    "All channel Sessions", "All channel Active Users (MAU)",
    "All channel Active Users Change Value", "Major Change Contribution channel",
    "Organic Channel sessions", "Organic channel active users",
    "Organic channel active users Change Value",
    "Direct Channel Active User", "Direct Change Value",
    "Referral Channel Active User", "Referral Change",
    "Organic Social channel Active user", "Organic Social change",
    "Paid Ads channel active user", "Paid Ads change",
    "Sum DAU (All)", "Avg DAU (All)", "DAU/MAU %",
]

COL_SUBDOMAIN = 2
COL_ALL_USERS = 4
COL_ORG_USERS = 8
COL_DIR_USERS = 10
COL_REF_USERS = 12
COL_SOC_USERS = 14
COL_PAID_USERS = 16


def get_month_range(ref_date):
    """Return (start, end) of previous month."""
    year, month = ref_date.year, ref_date.month
    if month == 1:
        year -= 1
        month = 12
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


def run_report(ga4, property_id, start, end, dimension_filter=None):
    """
    Query GA4 for sessions + active users over a date range.
    No date dimension — GA4 deduplicates active users correctly across the full period.
    """
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d")
        )],
        dimensions=[],  # No date dimension — deduplicates active users correctly
        metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
        dimension_filter=dimension_filter,
    )
    resp = ga4.run_report(req)
    if resp.rows:
        return (
            int(resp.rows[0].metric_values[0].value),
            int(resp.rows[0].metric_values[1].value)
        )
    return 0, 0


def run_daily_report(ga4, property_id, start, end, dimension_filter=None):
    """
    Query GA4 with date dimension to get daily active users.
    Used only for DAU/MAU calculation — sums daily rows intentionally.
    """
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d")
        )],
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
        dimension_filter=dimension_filter,
    )
    resp = ga4.run_report(req)
    sessions, users = 0, 0
    for row in resp.rows:
        sessions += int(row.metric_values[0].value)
        users    += int(row.metric_values[1].value)
    return sessions, users


def fetch_month(ga4, prop, start, end):
    pid = prop["ga4"]

    # Deduplicated metrics (correct active users)
    all_s,  all_u  = run_report(ga4, pid, start, end)
    org_s,  org_u  = run_report(ga4, pid, start, end, channel_filter(CHANNEL_ORGANIC_SEARCH))
    dir_s,  dir_u  = run_report(ga4, pid, start, end, channel_filter(CHANNEL_DIRECT))
    ref_s,  ref_u  = run_report(ga4, pid, start, end, channel_filter(CHANNEL_REFERRAL))
    soc_s,  soc_u  = run_report(ga4, pid, start, end, channel_filter(CHANNEL_ORGANIC_SOCIAL))
    paid_s, paid_u = run_report(ga4, pid, start, end, channel_filter(CHANNEL_PAID_SEARCH))

    # Sum of daily active users (for DAU/MAU numerator)
    _, sum_dau = run_daily_report(ga4, pid, start, end)
    days_in_period = (end - start).days + 1
    avg_dau = round(sum_dau / days_in_period, 1)

    # DAU/MAU % — average daily users as % of monthly unique users
    dau_mau = round(avg_dau / all_u * 100, 1) if all_u > 0 else 0

    return {
        "all_sessions": all_s,  "all_users": all_u,
        "org_sessions": org_s,  "org_users": org_u,
        "dir_users":    dir_u,  "ref_users": ref_u,
        "soc_users":    soc_u,  "paid_users": paid_u,
        "sum_dau":      sum_dau, "avg_dau": avg_dau, "dau_mau": dau_mau,
    }


def major_contributor(cur, prev):
    channels = {
        "Organic Search": cur["org_users"]  - prev.get("org_users", 0),
        "Direct":         cur["dir_users"]  - prev.get("dir_users", 0),
        "Referral":       cur["ref_users"]  - prev.get("ref_users", 0),
        "Organic Social": cur["soc_users"]  - prev.get("soc_users", 0),
        "Paid Search":    cur["paid_users"] - prev.get("paid_users", 0),
    }
    return max(channels, key=lambda k: abs(channels[k]))


def get_prev_from_sheet(sheets, tab, subdomain):
    rows = read_all_rows(sheets, tab)
    if len(rows) < 2:
        return None
    match = None
    for row in rows[1:]:
        if len(row) > COL_SUBDOMAIN and row[COL_SUBDOMAIN] == subdomain:
            match = row
    if not match:
        return None
    def si(idx):
        try: return int(match[idx]) if len(match) > idx else 0
        except: return 0
    return {
        "all_users":  si(COL_ALL_USERS),
        "org_users":  si(COL_ORG_USERS),
        "dir_users":  si(COL_DIR_USERS),
        "ref_users":  si(COL_REF_USERS),
        "soc_users":  si(COL_SOC_USERS),
        "paid_users": si(COL_PAID_USERS),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Reference date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    ref = date.fromisoformat(args.date) if args.date else date.today()
    cur_start, cur_end = get_month_range(ref)
    prev_ref   = date(cur_start.year, cur_start.month, 1) - timedelta(days=1)
    prev_start, prev_end = get_month_range(prev_ref)
    date_label = f"{cur_start} to {cur_end}"
    print(f"Running Monthly Site GA4 for {date_label}")

    ga4    = get_ga4_client()
    sheets = get_sheets_client()
    tab    = SHEET_NAMES["monthly_site_ga4"]
    ensure_headers(sheets, tab, HEADERS)

    rows = []
    for prop in PROPERTIES:
        print(f"  Fetching {prop['subdomain']}...")
        cur  = fetch_month(ga4, prop, cur_start, cur_end)
        prev = get_prev_from_sheet(sheets, tab, prop["subdomain"])
        if prev is None:
            print(f"    No prev data in sheet — fetching from API...")
            prev = fetch_month(ga4, prop, prev_start, prev_end)

        contrib = major_contributor(cur, prev)
        row = [
            date_label, prop["lan"], prop["subdomain"],
            cur["all_sessions"], cur["all_users"],
            cur["all_users"]  - prev["all_users"],  contrib,
            cur["org_sessions"], cur["org_users"],
            cur["org_users"]  - prev["org_users"],
            cur["dir_users"],  cur["dir_users"]  - prev["dir_users"],
            cur["ref_users"],  cur["ref_users"]  - prev["ref_users"],
            cur["soc_users"],  cur["soc_users"]  - prev["soc_users"],
            cur["paid_users"], cur["paid_users"] - prev["paid_users"],
            cur["sum_dau"], cur["avg_dau"], cur["dau_mau"],
        ]
        rows.append(row)

    append_rows(sheets, tab, rows)
    print(f"Monthly Site GA4 complete. {len(rows)} rows written.")


if __name__ == "__main__":
    main()
