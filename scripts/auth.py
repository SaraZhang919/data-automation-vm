"""
auth.py — Google service account authentication.
Reads GOOGLE_CREDENTIALS from environment (set as GitHub Secret).
Returns authorized clients for GA4, GSC, and Sheets APIs.
"""

import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.analytics.data_v1beta import BetaAnalyticsDataClient

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]


def get_credentials():
    """Load service account credentials from environment variable."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise EnvironmentError("GOOGLE_CREDENTIALS environment variable not set.")
    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    return credentials


def get_ga4_client():
    """Return authenticated GA4 Data API client."""
    credentials = get_credentials()
    return BetaAnalyticsDataClient(credentials=credentials)


def get_gsc_client():
    """Return authenticated GSC API client."""
    credentials = get_credentials()
    return build("searchconsole", "v1", credentials=credentials)


def get_sheets_client():
    """Return authenticated Google Sheets API client."""
    credentials = get_credentials()
    return build("sheets", "v4", credentials=credentials)
