"""n.a. is a Sheets display value; analytics continue to use missing values."""
from .layout import COUNTS, PERCENT

METRICS = COUNTS | PERCENT | {'position','averageSessionDuration','key_events_per_user',
    'baseline_clicks','baseline_impressions','impressions_daily_delta','impressions_growth_ratio',
    'total_sessions','total_bot_sessions','distinct_users','pages_per_session','active_time','total_time','average_scroll_depth'}
TABLES = {'GA4 Site','GA4 Channels','GA4 AI Traffic','GA4 Landing Pages','GA4 Events','GA4 Business Events',
          'GSC Site','GSC Pages','GSC Queries','Clarity Snapshots','Clarity Pages','Manual Results'}


def supported(name, key):
    if name not in TABLES:
        return False
    return key in METRICS or key in ('page_name','page_type') or (
        name.startswith('Clarity') and key.endswith(('_count','_session_rate','_sessions_base')))


def display(name, key, value):
    return 'n.a.' if supported(name,key) and value in ('',None) else value


def internal(name, key, value):
    return '' if supported(name,key) and value == 'n.a.' else value
