"""
thresholds.py — Alert threshold logic for Yellow and Red cell highlighting.
All thresholds match the Thresholds sheet exactly.
Returns 'yellow', 'red', or None.
"""


def _check(value, baseline, pct_thresh, abs_thresh):
    """Return True if change exceeds both percentage AND absolute thresholds."""
    if baseline == 0:
        return False
    pct = abs(value - baseline) / baseline
    abs_val = abs(value - baseline)
    return pct >= pct_thresh and abs_val >= abs_thresh


# ── Weekly by page - GA4 ─────────────────────────────────────────────────────

def weekly_page_all_channel_active_users(current, baseline):
    """Yellow/Red for All Channel Active Users — Weekly by page."""
    if baseline < 1000:
        if _check(current, baseline, 0.40, 400): return "red"
        if _check(current, baseline, 0.25, 150): return "yellow"
    elif baseline < 5000:
        if _check(current, baseline, 0.30, 1200): return "red"
        if _check(current, baseline, 0.18, 700):  return "yellow"
    elif baseline < 20000:
        if _check(current, baseline, 0.25, 3500): return "red"
        if _check(current, baseline, 0.12, 1800): return "yellow"
    else:
        if _check(current, baseline, 0.18, 10000): return "red"
        if _check(current, baseline, 0.10, 5000):  return "yellow"
    return None


def weekly_page_organic_active_users(current, baseline):
    """Yellow/Red for Organic Search Active Users — Weekly by page."""
    if baseline < 500:
        if _check(current, baseline, 0.50, 200): return "red"
        if _check(current, baseline, 0.35, 120): return "yellow"
    elif baseline < 2000:
        if _check(current, baseline, 0.30, 400): return "red"
        if _check(current, baseline, 0.20, 250): return "yellow"
    elif baseline < 10000:
        if _check(current, baseline, 0.25, 1000): return "red"
        if _check(current, baseline, 0.15, 700):  return "yellow"
    else:
        if _check(current, baseline, 0.18, 2200): return "red"
        if _check(current, baseline, 0.10, 1500): return "yellow"
    return None


def weekly_page_organic_active_users_page(current, baseline):
    """Orange(yellow)/Red for Organic Active Users at page level — Weekly by page."""
    if baseline < 100:
        if _check(current, baseline, 0.65, 70): return "red"
        return None  # ignore yellow
    elif baseline < 500:
        if _check(current, baseline, 0.45, 180): return "red"
        if _check(current, baseline, 0.30, 100): return "yellow"
    elif baseline < 2000:
        if _check(current, baseline, 0.40, 500): return "red"
        if _check(current, baseline, 0.25, 250): return "yellow"
    else:
        if _check(current, baseline, 0.30, 1200): return "red"
        if _check(current, baseline, 0.20, 600):  return "yellow"
    return None


def weekly_page_engagement_ratio(current_rate, baseline_rate, baseline_sessions):
    """Orange(yellow)/Red for Engagement Rate — Weekly by page. Rates in 0-100 scale (pp)."""
    if baseline_sessions < 100:
        return None  # ignore
    diff = abs(current_rate - baseline_rate)
    if baseline_sessions < 500:
        if diff >= 12: return "yellow"  # 100-499: only yellow, no red
        return None
    if diff >= 12: return "red"
    if diff >= 8:  return "yellow"
    return None


def weekly_page_key_events(current, baseline):
    """Orange(yellow)/Red for Key Events — Weekly by page."""
    if baseline < 20:
        if _check(current, baseline, 0.60, 12): return "red"
        return None  # ignore yellow
    elif baseline < 100:
        if _check(current, baseline, 0.60, 35): return "red"
        if _check(current, baseline, 0.40, 20): return "yellow"
    elif baseline < 500:
        if _check(current, baseline, 0.45, 120): return "red"
        if _check(current, baseline, 0.30, 60):  return "yellow"
    else:
        if _check(current, baseline, 0.35, 300): return "red"
        if _check(current, baseline, 0.20, 150): return "yellow"
    return None


# ── Weekly by page - GSC ─────────────────────────────────────────────────────

def weekly_page_gsc_impressions(current, baseline):
    """Orange(yellow)/Red for GSC Impressions — Weekly by page."""
    if baseline < 500:
        if _check(current, baseline, 0.70, 350): return "red"
        if _check(current, baseline, 0.50, 200): return "yellow"
    elif baseline < 3000:
        if _check(current, baseline, 0.45, 1200): return "red"
        if _check(current, baseline, 0.30, 700):  return "yellow"
    elif baseline < 10000:
        if _check(current, baseline, 0.35, 4000): return "red"
        if _check(current, baseline, 0.25, 1500): return "yellow"
    else:
        if _check(current, baseline, 0.28, 6000): return "red"
        if _check(current, baseline, 0.18, 3000): return "yellow"
    return None


def weekly_page_gsc_position(current_pos, baseline_pos):
    """Orange(yellow)/Red for GSC Position — Weekly by page. Lower position = better."""
    diff = abs(current_pos - baseline_pos)
    if baseline_pos <= 2:
        if diff >= 1.0: return "red"
    elif baseline_pos <= 5:
        if diff >= 1.5: return "red"
    elif baseline_pos <= 10:
        if diff >= 2.5: return "red"
    elif baseline_pos <= 20:
        if diff >= 4.0: return "red"
    else:
        if diff >= 10: return "yellow"
    return None


# ── Weekly brand by impressions ───────────────────────────────────────────────

def weekly_brand_clicks(current, baseline):
    """Orange(yellow)/Red for Brand Query Clicks — Weekly."""
    if baseline < 50:
        return None  # ignore
    elif baseline < 200:
        if _check(current, baseline, 0.65, 60):  return "red"
        if _check(current, baseline, 0.45, 35):  return "yellow"
    elif baseline < 1000:
        if _check(current, baseline, 0.50, 200): return "red"
        if _check(current, baseline, 0.35, 100): return "yellow"
    elif baseline < 5000:
        if _check(current, baseline, 0.40, 600): return "red"
        if _check(current, baseline, 0.28, 300): return "yellow"
    elif baseline < 20000:
        if _check(current, baseline, 0.32, 1200): return "red"
        if _check(current, baseline, 0.22, 800):  return "yellow"
    else:
        if _check(current, baseline, 0.25, 4000): return "red"
        if _check(current, baseline, 0.18, 2500): return "yellow"
    return None


# ── 4-week Site - GA4 ─────────────────────────────────────────────────────────

def monthly_site_all_channel_active_users(current, baseline):
    if baseline < 4000:
        if _check(current, baseline, 0.30, 1200): return "red"
        if _check(current, baseline, 0.18, 500):  return "yellow"
    elif baseline < 20000:
        if _check(current, baseline, 0.25, 3000): return "red"
        if _check(current, baseline, 0.15, 1500): return "yellow"
    elif baseline < 80000:
        if _check(current, baseline, 0.18, 8000): return "red"
        if _check(current, baseline, 0.10, 4000): return "yellow"
    else:
        if _check(current, baseline, 0.15, 20000): return "red"
        if _check(current, baseline, 0.08, 12000): return "yellow"
    return None


def monthly_site_organic_active_users(current, baseline):
    if baseline < 2000:
        if _check(current, baseline, 0.40, 800): return "red"
        if _check(current, baseline, 0.25, 400): return "yellow"
    elif baseline < 8000:
        if _check(current, baseline, 0.30, 2000): return "red"
        if _check(current, baseline, 0.18, 1000): return "yellow"
    elif baseline < 40000:
        if _check(current, baseline, 0.22, 5000): return "red"
        if _check(current, baseline, 0.12, 2500): return "yellow"
    else:
        if _check(current, baseline, 0.18, 10000): return "red"
        if _check(current, baseline, 0.10, 6000):  return "yellow"
    return None


# ── 4-week page - GA4 ─────────────────────────────────────────────────────────

def monthly_page_engagement_ratio(current_rate, baseline_rate, baseline_sessions):
    if baseline_sessions < 400:
        return None
    elif baseline_sessions < 2000:
        diff = abs(current_rate - baseline_rate)
        if diff >= 10: return "red"
        if diff >= 6:  return "yellow"
    else:
        diff = abs(current_rate - baseline_rate)
        if diff >= 8: return "red"
        if diff >= 5: return "yellow"
    return None


def monthly_page_key_events(current, baseline):
    if baseline < 80:
        if _check(current, baseline, 0.50, 40): return "red"
        return None
    elif baseline < 400:
        if _check(current, baseline, 0.50, 150): return "red"
        if _check(current, baseline, 0.35, 80):  return "yellow"
    elif baseline < 2000:
        if _check(current, baseline, 0.40, 500): return "red"
        if _check(current, baseline, 0.25, 250): return "yellow"
    else:
        if _check(current, baseline, 0.30, 1500): return "red"
        if _check(current, baseline, 0.18, 700):  return "yellow"
    return None


def monthly_page_organic_active_users(current, baseline):
    if baseline < 400:
        if _check(current, baseline, 0.55, 200): return "red"
        return None
    elif baseline < 2000:
        if _check(current, baseline, 0.40, 700): return "red"
        if _check(current, baseline, 0.25, 300): return "yellow"
    elif baseline < 8000:
        if _check(current, baseline, 0.35, 2200): return "red"
        if _check(current, baseline, 0.20, 1000): return "yellow"
    else:
        if _check(current, baseline, 0.28, 5000): return "red"
        if _check(current, baseline, 0.15, 2500): return "yellow"
    return None


# ── 4-week by page - GSC ──────────────────────────────────────────────────────

def monthly_page_gsc_impressions(current, baseline):
    if baseline < 2000:
        if _check(current, baseline, 0.60, 1500): return "red"
        if _check(current, baseline, 0.40, 800):  return "yellow"
    elif baseline < 12000:
        if _check(current, baseline, 0.40, 5000): return "red"
        if _check(current, baseline, 0.25, 2500): return "yellow"
    elif baseline < 40000:
        if _check(current, baseline, 0.30, 12000): return "red"
        if _check(current, baseline, 0.20, 6000):  return "yellow"
    else:
        if _check(current, baseline, 0.25, 25000): return "red"
        if _check(current, baseline, 0.15, 15000): return "yellow"
    return None


def monthly_page_gsc_position(current_pos, baseline_pos):
    diff = abs(current_pos - baseline_pos)
    if baseline_pos <= 2:
        if diff >= 0.8: return "red"
    elif baseline_pos <= 5:
        if diff >= 1.2: return "red"
    elif baseline_pos <= 10:
        if diff >= 2.0: return "red"
    elif baseline_pos <= 20:
        if diff >= 3.0: return "red"
    else:
        if diff >= 8: return "yellow"
    return None


# ── 4-week brand clicks ───────────────────────────────────────────────────────

def monthly_brand_clicks(current, baseline):
    if baseline < 200:
        return None
    elif baseline < 800:
        if _check(current, baseline, 0.50, 250): return "red"
        if _check(current, baseline, 0.35, 120): return "yellow"
    elif baseline < 4000:
        if _check(current, baseline, 0.40, 800): return "red"
        if _check(current, baseline, 0.28, 400): return "yellow"
    elif baseline < 20000:
        if _check(current, baseline, 0.32, 2500): return "red"
        if _check(current, baseline, 0.22, 1200): return "yellow"
    elif baseline < 80000:
        if _check(current, baseline, 0.28, 7000): return "red"
        if _check(current, baseline, 0.18, 3500): return "yellow"
    else:
        if _check(current, baseline, 0.22, 15000): return "red"
        if _check(current, baseline, 0.15, 8000):  return "yellow"
    return None
