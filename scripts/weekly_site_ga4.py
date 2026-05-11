"""
weekly_site_ga4.py — Pull GA4 weekly site-level data per subdomain.
Date range: Last Sunday to this Saturday.
Schedule: Every Sunday at 4PM JST.
First run: pulls both current and previous week from API.
Subsequent runs: reads previous week values from sheet.
"""

import argparse
from datetime import date, timedelta
from google.analytics.data_v1beta.types import (
    RunReportRequest, Dimension, Metric, DateRange,
    FilterExpression, Filter
)
from auth import get_ga4_client, get_sheets_client
from config import PROPERTIES, SHEET_NAMES, GA4_CHANNEL_DIM
from config import CHANNEL_ORGANIC_SEARCH, CHANNEL_DIRECT, CHANNEL_REFERRAL
from config import CHANNEL_ORGANIC_SOCIAL, CHANNEL_PAID_SEARCH
from sheets import ensure_headers, append_rows, read_all_rows

HEADERS = [
    "Date", "Lan", "Subdomain",
    "All channel Sessions", "All channel Active Users",
    "All channel Active Users Change Value", "Major Change Contribution channel",
    "Organic Channel sessions", "Organic channel active users",
    "Organic channel active users Change Value",
    "Direct Channel Active User", "Direct Change Value",
    "Referral Channel Active User", "Referral Change",
    "Organic Social channel Active user", "Organic Social change",
    "Paid Ads channel active user", "Paid Ads change",
]

# Column indices for reading previous week values (0-based)
COL_SUBDOMAIN = 2
COL_ALL_USERS = 4
COL_ORG_USERS = 8
COL_DIR_USERS = 10
COL_REF_USERS = 12
COL_SOC_USERS = 14
COL_PAID_USERS = 16


def get_week_range(ref_date):
    """
    Return (start, end) for the most recent complete Sun–Sat week before ref_date.
    Sunday 2026-05-10 → 2026-05-03 to 2026-05-09.
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


def run_report(ga4, property_id, start_date, end_date, dimension_filter=None):
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d")
        )],
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
        dimension_filter=dimension_filter,
    )
    resp = ga4.run_report(req)
    sessions, users = 0, 0
    for row in resp.rows:
        sessions += int(row.metric_values[0].value)
        users += int(row.metric_values[1].value)
    return sessions, users


def fetch_week(ga4, prop, start, end):
    pid = prop["ga4"]
    all_s, all_u = run_report(ga4, pid, start, end)
    org_s, org_u = run_report(ga4, pid, start, end, channel_filter(CHANNEL_ORGANIC_SEARCH))
    dir_s, dir_u = run_report(ga4, pid, start, end, channel_filter(CHANNEL_DIRECT))
    ref_s, ref_u = run_report(ga4, pid, start, end, channel_filter(CHANNEL_REFERRAL))
    soc_s, soc_u = run_report(ga4, pid, start, end, channel_filter(CHANNEL_ORGANIC_SOCIAL))
    paid_s, paid_u = run_report(ga4, pid, start, end, channel_filter(CHANNEL_PAID_SEARCH))
    return {
        "all_sessions": all_s, "all_users": all_u,
        "org_sessions": org_s, "org_users": org_u,
        "dir_users": dir_u,
        "ref_users": ref_u,
        "soc_users": soc_u,
        "paid_users": paid_u,
    }


def major_contributor(cur, prev):
    """Return the channel with the largest absolute change."""
    channels = {
        "Organic Search": cur["org_users"] - prev.get("org_users", 0),
        "Direct":         cur["dir_users"] - prev.get("dir_users", 0),
        "Referral":       cur["ref_users"] - prev.get("ref_users", 0),
        "Organic Social": cur["soc_users"] - prev.get("soc_users", 0),
        "Paid Search":    cur["paid_users"] - prev.get("paid_users", 0),
    }
    return max(channels, key=lambda k: abs(channels[k]))


def get_prev_from_sheet(sheets, tab, subdomain):
    """Read previous week values for a subdomain from the sheet."""
    rows = read_all_rows(sheets, tab)
    if len(rows) < 2:
        return None
    # Find last row matching subdomain
    match = None
    for row in rows[1:]:
        if len(row) > COL_SUBDOMAIN and row[COL_SUBDOMAIN] == subdomain:
            match = row
    if not match:
        return None

    def safe_int(val):
        try: return int(val)
        except: return 0

    return {
        "all_users":  safe_int(match[COL_ALL_USERS]  if len(match) > COL_ALL_USERS  else 0),
        "org_users":  safe_int(match[COL_ORG_USERS]  if len(match) > COL_ORG_USERS  else 0),
        "dir_users":  safe_int(match[COL_DIR_USERS]  if len(match) > COL_DIR_USERS  else 0),
        "ref_users":  safe_int(match[COL_REF_USERS]  if len(match) > COL_REF_USERS  else 0),
        "soc_users":  safe_int(match[COL_SOC_USERS]  if len(match) > COL_SOC_USERS  else 0),
        "paid_users": safe_int(match[COL_PAID_USERS] if len(match) > COL_PAID_USERS else 0),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Reference Sunday YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    ref = date.fromisoformat(args.date) if args.date else date.today()
    cur_start, cur_end = get_week_range(ref)
    prev_start = cur_start - timedelta(days=7)
    prev_end = cur_end - timedelta(days=7)
    date_label = f"{cur_start} to {cur_end}"
    print(f"Running Weekly Site GA4 for {date_label}")

    ga4 = get_ga4_client()
    sheets = get_sheets_client()
    tab = SHEET_NAMES["weekly_site_ga4"]
    ensure_headers(sheets, tab, HEADERS)

    rows = []
    for prop in PROPERTIES:
        print(f"  Fetching {prop['subdomain']}...")
        cur = fetch_week(ga4, prop, cur_start, cur_end)

        # Try to get previous week from sheet first
        prev = get_prev_from_sheet(sheets, tab, prop["subdomain"])
        if prev is None:
            print(f"    No prev data in sheet — fetching from API...")
            prev = fetch_week(ga4, prop, prev_start, prev_end)

        contrib = major_contributor(cur, prev)
        row = [
            date_label, prop["lan"], prop["subdomain"],
            cur["all_sessions"], cur["all_users"],
            cur["all_users"] - prev["all_users"], contrib,
            cur["org_sessions"], cur["org_users"],
            cur["org_users"] - prev["org_users"],
            cur["dir_users"], cur["dir_users"] - prev["dir_users"],
            cur["ref_users"], cur["ref_users"] - prev["ref_users"],
            cur["soc_users"], cur["soc_users"] - prev["soc_users"],
            cur["paid_users"], cur["paid_users"] - prev["paid_users"],
        ]
        rows.append(row)

    append_rows(sheets, tab, rows)
    print(f"Weekly Site GA4 complete. {len(rows)} rows written.")


if __name__ == "__main__":
    main()
