"""
daily_ga4.py — Pull GA4 data by subdomain for yesterday, write to Daily sheet.
Schedule: Every day at 4PM JST (07:00 UTC).
Manual trigger: pass --date YYYY-MM-DD for any specific date.
"""

import sys
import argparse
from datetime import date, timedelta
from google.analytics.data_v1beta.types import (
    RunReportRequest, Dimension, Metric, DateRange, FilterExpression,
    Filter, FilterExpressionList
)
from auth import get_ga4_client, get_sheets_client
from config import PROPERTIES, SHEET_NAMES, GA4_CHANNEL_DIM
from config import CHANNEL_ORGANIC_SEARCH, CHANNEL_DIRECT, CHANNEL_REFERRAL, CHANNEL_PAID_SEARCH

SESSION_CHANNEL_DIM = "sessionDefaultChannelGroup"
from sheets import ensure_headers, append_rows

HEADERS = [
    "Date", "Lan", "Subdomain",
    "All channel Sessions", "All channel Active Users",
    "Acq Organic Sessions", "Acq Organic Active Users", "Acq Organic New Users",
    "Direct Sessions", "Direct Channel Active User",
    "Referral Channel Active User",
    "Paid Ads channel active user",
    "Session Organic Sessions", "Session Organic Active Users", "Session Organic New Users",
]


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


def session_channel_filter(channel_value):
    """Filter by sessionDefaultChannelGroup instead of firstUserDefaultChannelGroup."""
    return FilterExpression(
        filter=Filter(
            field_name=SESSION_CHANNEL_DIM,
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value=channel_value
            )
        )
    )


def run_report(ga4, property_id, start_date, end_date, dimension_filter=None):
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name="date")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="activeUsers"),
        ],
        dimension_filter=dimension_filter,
    )
    resp = ga4.run_report(req)
    if resp.rows:
        return int(resp.rows[0].metric_values[0].value), int(resp.rows[0].metric_values[1].value)
    return 0, 0


def run_report_with_new_users(ga4, property_id, start_date, end_date, dimension_filter=None):
    """Fetch sessions, activeUsers and newUsers in one call."""
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name="date")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="activeUsers"),
            Metric(name="newUsers"),
        ],
        dimension_filter=dimension_filter,
    )
    resp = ga4.run_report(req)
    if resp.rows:
        return (int(resp.rows[0].metric_values[0].value),
                int(resp.rows[0].metric_values[1].value),
                int(resp.rows[0].metric_values[2].value))
    return 0, 0, 0


def fetch_daily(ga4, prop, target_date):
    pid = prop["ga4"]
    d = target_date.strftime("%Y-%m-%d")

    all_sessions, all_users                     = run_report(ga4, pid, d, d)
    acq_org_s, acq_org_u, acq_org_new_u         = run_report_with_new_users(ga4, pid, d, d, channel_filter(CHANNEL_ORGANIC_SEARCH))
    dir_sessions, dir_users                      = run_report(ga4, pid, d, d, channel_filter(CHANNEL_DIRECT))
    ref_sessions, ref_users                      = run_report(ga4, pid, d, d, channel_filter(CHANNEL_REFERRAL))
    paid_sessions, paid_users                    = run_report(ga4, pid, d, d, channel_filter(CHANNEL_PAID_SEARCH))
    ses_org_s, ses_org_u, ses_org_new_u          = run_report_with_new_users(ga4, pid, d, d, session_channel_filter(CHANNEL_ORGANIC_SEARCH))

    return [
        d,
        prop["lan"],
        prop["subdomain"],
        all_sessions, all_users,
        acq_org_s, acq_org_u, acq_org_new_u,
        dir_sessions, dir_users,
        ref_users,
        paid_users,
        ses_org_s, ses_org_u, ses_org_new_u,
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()

    target_date = (date.fromisoformat(args.date) if args.date else date.today()) - timedelta(days=1)
    print(f"Running Daily GA4 for {target_date}")

    ga4 = get_ga4_client()
    sheets = get_sheets_client()
    tab = SHEET_NAMES["daily"]

    ensure_headers(sheets, tab, HEADERS)

    rows = []
    for prop in PROPERTIES:
        print(f"  Fetching {prop['subdomain']}...")
        row = fetch_daily(ga4, prop, target_date)
        rows.append(row)

    append_rows(sheets, tab, rows)
    print(f"Daily GA4 complete. {len(rows)} rows written.")


if __name__ == "__main__":
    main()
