# CHANGELOG.md

## Session 1 — Initial Build
**Date:** 2026-05-09
**What was built:**
- Full project architecture designed and confirmed
- All 8 scheduled jobs defined
- Complete repo structure created:
  - `scripts/config.py` — property config
  - `scripts/auth.py` — service account auth
  - `scripts/sheets.py` — sheet read/write/highlight helpers
  - `scripts/thresholds.py` — Yellow/Red alert logic
  - `scripts/daily_ga4.py` — daily GA4 job
  - `scripts/weekly_site_ga4.py` — weekly site GA4
  - `scripts/weekly_page_ga4.py` — weekly page GA4
  - `scripts/weekly_page_gsc.py` — weekly page GSC
  - `scripts/weekly_brand_gsc.py` — weekly brand queries
  - `scripts/monthly_site_ga4.py` — monthly site GA4
  - `scripts/monthly_page_ga4.py` — monthly page GA4
  - `scripts/monthly_page_gsc.py` — monthly page GSC
  - GitHub Actions workflows for all schedules
  - `CONTEXT.md`, `CHANGELOG.md`, `README.md`

**Key decisions confirmed this session:**
- Service account auth (not OAuth)
- Public repo, credentials in GitHub Secrets
- Yellow + Red alerts, highlighting only
- All monthly jobs on 4th of month
- Organic Search filter for engagement metrics
- Top 30 pages + Page name sheet URLs, merged
- Manual workflow_dispatch trigger for testing

---
<!-- Add new sessions below this line -->

## Session 3 — Fix Weekly Date Range Bug
**Date:** 2026-05-11

### Bug Fixed
**All 4 weekly scripts had wrong `get_week_range()` logic.**

- **Root cause:** `weekly_site_ga4.py` and `weekly_page_ga4.py` used `(dow + 1) % 7` which returns 0 when run on Sunday, so start = Sunday itself → range was current week not previous week.
- **Symptom:** Running on Sunday 2026-05-10 produced date range `2026-05-10 to 2026-05-16` instead of `2026-05-03 to 2026-05-09`.
- `weekly_page_gsc.py` and `weekly_brand_gsc.py` had a slightly different formula that was correct for Tuesday but untested for other days.

### Fix Applied
Replaced all 4 `get_week_range()` functions with one canonical implementation:
```python
def get_week_range(ref_date):
    dow = ref_date.weekday()  # Mon=0 ... Sat=5, Sun=6
    days_back_to_sat = (dow - 5) % 7
    if days_back_to_sat == 0:
        days_back_to_sat = 7
    end = ref_date - timedelta(days=days_back_to_sat)
    start = end - timedelta(days=6)
    return start, end
```
**Verified manually:**
- Sunday May 10 → end = May 9 (Sat), start = May 3 ✅
- Tuesday May 12 → end = May 9 (Sat), start = May 3 ✅
- Saturday May 9 → end = May 2 (Sat), start = Apr 26 ✅ (goes to previous Saturday)

### Files Changed
- `scripts/weekly_site_ga4.py`
- `scripts/weekly_page_ga4.py`
- `scripts/weekly_page_gsc.py`
- `scripts/weekly_brand_gsc.py`

### GSC Data Note
GSC data for a given week is typically available 2–3 days after the week ends. The Tuesday run schedule accounts for this — running Tuesday to cover Sun–Sat of the previous week gives GSC enough time to finalize the data. No schedule change needed.


---

## Session 4 — Multi-value Filter for Manual Check Scripts
**Date:** 2026-05-11

### Changed
- `scripts/manual_check_ga4.py` — added `--page_names` and `--url_filter` arguments supporting pipe-separated values
- `scripts/manual_check_gsc.py` — same

### How it works
- `--page_names "homepage|onlinetool"` — matches the Page Name column (case-insensitive)
- `--url_filter "/home|/tool"` — matches URL substring (case-insensitive)
- Both use OR logic: a page is included if it matches any value in either filter
- If neither filter is set: all pages included (original behaviour preserved)
- When a filter is active, the top-30 API call is skipped — saves quota and runs faster

### No yml changes needed
The manual_check.yml workflow already passes --page_names and --url_filter as optional inputs. Leave blank for no filtering.

---

## Session 5 — Multi-value Filter for Manual Page Detail Scripts
**Date:** 2026-05-11

### Changed
- `scripts/manual_page_detail_ga4.py` — `--page_name` and `--url_filter` now support pipe-separated values
- `scripts/manual_page_detail_gsc.py` — same

### How it works
- `--page_name "Home|Online Tool"` — matches the Page Name column (case-insensitive), OR logic
- `--url_filter "/home|/tool"` — substring match on URL (case-sensitive), OR logic
- Single values still work exactly as before (backward compatible)
- If neither filter matches anything, script exits with a clear message

### No yml changes needed
`manual_page_detail.yml` already passes `--page_name` and `--url_filter` as inputs. Pipe-separated values work as-is.
