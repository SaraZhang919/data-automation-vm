"""
config.py — Central configuration for all Vidmud properties and sheet names.
To add/remove subdomains, edit PROPERTIES only. Everything else reads from here.
"""

PROPERTIES = [
    {"lan": "EN", "subdomain": "www.vidmud.com",  "gsc": "sc-domain:vidmud.com",         "ga4": "438691348"},
    {"lan": "DE", "subdomain": "de.vidmud.com",   "gsc": "https://de.vidmud.com/",        "ga4": "459413242"},
    {"lan": "FR", "subdomain": "fr.vidmud.com",   "gsc": "https://fr.vidmud.com/",        "ga4": "459379487"},
    {"lan": "ES", "subdomain": "es.vidmud.com",   "gsc": "https://es.vidmud.com/",        "ga4": "459417270"},
    {"lan": "IT", "subdomain": "it.vidmud.com",   "gsc": "https://it.vidmud.com/",        "ga4": "459369622"},
    {"lan": "JP", "subdomain": "jp.vidmud.com",   "gsc": "https://jp.vidmud.com/",        "ga4": "459364055"},
    {"lan": "TW", "subdomain": "tw.vidmud.com",   "gsc": "https://tw.vidmud.com/",        "ga4": "459389514"},
    {"lan": "AR", "subdomain": "ar.vidmud.com",   "gsc": "https://ar.vidmud.com/",        "ga4": "459394157"},
    {"lan": "KR", "subdomain": "kr.vidmud.com",   "gsc": "https://kr.vidmud.com/",        "ga4": "459392728"},
    {"lan": "PT", "subdomain": "pt.vidmud.com",   "gsc": "https://pt.vidmud.com/",        "ga4": "459404147"},
]

SHEET_NAMES = {
    "page_names":        "Page name - manual management",
    "event_logs":        "Site Event Logs-Manual",
    "weekly_site_ga4":   "Weekly Site - GA4",
    "weekly_page_ga4":   "Weekly by page - GA4",
    "weekly_page_gsc":   "Weekly by page - GSC",
    "weekly_brand":      "Weekly brand by impressions",
    "daily":             "Daily",
    "monthly_site_ga4":  "4-week Site - GA4",
    "monthly_page_ga4":  "4-week page - GA4",
    "monthly_page_gsc":  "4-week by page - GSC",
    "thresholds":        "Thresholds",
}

# GA4 channel group dimension name
GA4_CHANNEL_DIM = "firstUserDefaultChannelGroup"

# GA4 channel filter values
CHANNEL_ORGANIC_SEARCH = "Organic Search"
CHANNEL_DIRECT         = "Direct"
CHANNEL_REFERRAL       = "Referral"
CHANNEL_ORGANIC_SOCIAL = "Organic Social"
CHANNEL_PAID_SEARCH    = "Paid Search"

# GSC brand query filters
BRAND_EXACT    = "Vidmud"
BRAND_CONTAINS = "vidmud"  # GSC queries are lowercase

# Pages: how many top organic pages to pull per subdomain
TOP_PAGES_COUNT = 30

# Alert colors (Google Sheets RGB)
COLOR_YELLOW = {"red": 1.0,  "green": 0.949, "blue": 0.4}
COLOR_RED    = {"red": 0.918, "green": 0.263, "blue": 0.208}
COLOR_NONE   = {"red": 1.0,  "green": 1.0,   "blue": 1.0}
