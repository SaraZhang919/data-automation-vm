import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

LAUNCH = date(2026, 9, 7)
SITE = "https://www.iboomto.com"
DATA_ID = "1Iw07GRTmwK4GoE3zPpGYG-rdneBHchYIb6-s-knFLvs"
SF_FOLDER = "1QKOgh4aFtVM1CQqaqdwlVSklq8s4LiND"
PARENT_FOLDER = "1Gqfn-YHyK5v7JimX-EZHHxYcICeRhc_C"
LANGS = ("en", "ar", "ja", "zh-tw", "es", "de", "fr", "it", "pt")
MODEL = "gpt-5.6-sol"
PROMPT_VERSION = "iboomto-2026-09-v4"
RULE_VERSION = "launch-v1"

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:24]

def load_local_env(path):
    # Explicit opt-in for local use; never logs values or copies key files.
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if re.match(r"^[A-Z_]+=", line):
            name, value = line.split("=", 1)
            os.environ.setdefault(name, value.strip().strip('"').strip("'"))

def language(url):
    p = urlsplit(url)
    if p.netloc and p.netloc.lower() != "www.iboomto.com":
        return None
    if re.search(r"\.(?:js|css|png|jpg|jpeg|svg|ico|woff2?|exe|msi|zip|xml|webp)$", p.path, re.I):
        return None
    segment = p.path.split("/")[1] if p.path.startswith("/") else p.path.split("/")[0]
    return segment if segment in LANGS[1:] else "en"

def parse_properties(rows):
    props = []
    for row in rows:
        if str(row.get("Platform", "")).upper() not in ("GA", "GA4"):
            continue
        lang = str(row.get("Language", "")).lower().strip()
        lang = "pt" if lang == "br" else lang
        pid = str(row.get("ID", "")).strip()
        if lang not in LANGS or not pid.isdigit():
            raise ValueError("Invalid Properties language or numeric GA4 ID")
        props.append({"language": lang, "id": pid, "homepage": row.get("Homepage", ""), "name": row.get("Name", "")})
    if {p['language'] for p in props} != set(LANGS) or len(props) != 9:
        raise ValueError("Properties must contain exactly nine iBoomto GA4 languages")
    if len({p['id'] for p in props}) != 9:
        raise ValueError("GA4 property IDs must be distinct")
    return props

def days(start, end):
    return [start + timedelta(days=i) for i in range(max(0, (end-start).days+1))]

def daily_window(now, tz):
    end = now.astimezone(ZoneInfo(tz)).date() - timedelta(days=1)
    return max(LAUNCH, end-timedelta(days=6)), end

def gsc_final_row(row):
    """Legacy preview rows stay in storage but must not drive current reports."""
    if row.get('quality')=='provisional':return False
    if row.get('quality')=='final':return True
    return bool(row.get('end') and row.get('final_through') and row['end']<=row['final_through'])

def previous_week(ref):
    end = ref - timedelta(days=(ref.weekday()-5) % 7 or 7)
    return end-timedelta(days=6), end

def previous_month(ref):
    end = ref.replace(day=1)-timedelta(days=1)
    return end.replace(day=1), end

def mature(end, tz, now):
    closed = datetime.combine(end+timedelta(days=1), datetime.min.time(), ZoneInfo(tz))
    return now-closed >= timedelta(hours=48)

def select_url(url, lang="all", exact="", prefix=""):
    return (language(url) is not None and (lang == "all" or language(url) == lang)
            and (not exact or url == exact) and (not prefix or urlsplit(url).path.startswith(prefix)))

def count_alert(current, baseline, metric="sessions", rules=None):
    if baseline <= 0:
        return "new_signal" if current > 0 else "observe"
    if baseline < (100 if metric == "impressions" else 20):
        return "observe"
    tiers = rules or [(20,100,.5,20,.7,40),(100,1000,.3,30,.5,50),(1000,float('inf'),.2,200,.35,350)]
    drop = baseline-current
    for low, high, yellow, ya, red, ra in tiers:
        if low <= baseline < high:
            if drop >= ra and drop/baseline >= red: return "red"
            if drop >= ya and drop/baseline >= yellow: return "yellow"
    return "normal"

def issue(kind, url, severity, evidence, observed_at, source="Technical Checks"):
    return {"id": digest([kind,url]), "kind": kind, "url": url, "severity": severity,
            "evidence": evidence, "observed_at": observed_at, "source": source}

