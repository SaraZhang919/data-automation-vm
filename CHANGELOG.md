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

## Session 2 — Bug Fixes, Manual Check & Page Detail Tools
**Date:** 2026-05-09

### Fixed
- All workflow files: replaced `GOOGLE_APPLICATION_CREDENTIALS` with `GOOGLE_CREDENTIALS` to match how `auth.py` reads credentials directly from the environment variable
- All workflow files: added `--date` flag to manual trigger script calls to match argparse usage in scripts
- Removed unnecessary "Write Google credentials" and "Clean up credentials" steps from all workflows
- Fixed YAML indentation error in `weekly_sunday.yml` that caused workflow to disappear from Actions tab

### Added
- `.gitignore` — prevents accidental credential commits
- `scripts/manual_check_ga4.py` — GA4 by page for any custom date range
- `scripts/manual_check_gsc.py` — GSC by page for any custom date range
- `scripts/manual_page_detail_ga4.py` — GA4 daily breakdown + summary filtered by page name
- `scripts/manual_page_detail_gsc.py` — GSC daily breakdown + summary filtered by page name
- `.github/workflows/manual_check.yml` — manual workflow with `start_date`, `end_date`, `data_source` inputs
- `.github/workflows/manual_page_detail.yml` — manual workflow with `start_date`, `end_date`, `page_name`, `url_filter`, `data_source` inputs
- Added `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` to new workflows
- New sheet tabs required: `Manual check - GA4`, `Manual check - GSC`, `Manual page detail - GA4`, `Manual page detail - GSC`

---

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
- Saturday May 9 → end = May 2 (Sat), start = Apr 26 ✅

### Files Changed
- `scripts/weekly_site_ga4.py`
- `scripts/weekly_page_ga4.py`
- `scripts/weekly_page_gsc.py`
- `scripts/weekly_brand_gsc.py`

### GSC Data Note
GSC data for a given week is typically available 2–3 days after the week ends. The Tuesday run schedule accounts for this. No schedule change needed.

---

## Session 4 — Multi-value Filter for Manual Check Scripts
**Date:** 2026-05-11

### Changed
- `scripts/manual_check_ga4.py` — `--page_names` and `--url_filter` now support pipe-separated values
- `scripts/manual_check_gsc.py` — same

### How it works
- `--page_names "homepage|onlinetool"` — matches Page Name column (case-insensitive), OR logic
- `--url_filter "/home|/tool"` — matches URL substring, OR logic
- Single values still work as before (backward compatible)

---

## Session 5 — Multi-value Filter for Manual Page Detail Scripts
**Date:** 2026-05-11

### Changed
- `scripts/manual_page_detail_ga4.py` — `--page_name` and `--url_filter` now support pipe-separated values
- `scripts/manual_page_detail_gsc.py` — same

### How it works
- `--page_name "Home|Online Tool"` — matches Page Name column (case-insensitive), OR logic
- `--url_filter "/home|/tool"` — substring match on URL, OR logic
- Single values still work exactly as before (backward compatible)

---

## Session 6 — Active Users Bug Fix + DAU/WAU and DAU/MAU Stickiness Metrics
**Date:** 2026-05-12

### Bug Fixed — Active Users Double-Counting
**Root cause:** `weekly_site_ga4.py` and `monthly_site_ga4.py` both used `dimensions=[Dimension(name="date")]` in `run_report()` and summed all daily rows. Since Active Users is a unique-user metric, a user active on multiple days was counted once per day — inflating weekly/monthly active user counts by ~25%.

**Confirmed via comparison:** Script reported 4,377 all-channel active users vs GA4's correct 3,486 for www.vidmud.com, week of May 3–9.

**Fix:** Removed `date` dimension from `run_report()` in both scripts. GA4 now returns one aggregated row per period, deduplicating users correctly across the full date range.

**Not affected:** `daily_ga4.py` (single-day queries), `weekly_page_ga4.py` and `monthly_page_ga4.py` (use `pagePath` dimension, not date), all GSC scripts (no active users concept).

### Added — DAU/WAU and DAU/MAU Stickiness Metrics
New `run_daily_sum()` function added to both site scripts — intentionally sums daily active users across the period (the "old" inflated number, now used purposefully as the DAU numerator).

**Formula:** `DAU/WAU % = Sum DAU / WAU × 100` (no division by 7 needed)

**New columns added to `Weekly Site - GA4`:**
- `Sum DAU (All)` — sum of daily all-channel active users
- `DAU/WAU % (All)` — all-channel stickiness
- `Sum DAU (Organic)` — sum of daily organic active users
- `DAU/WAU % (Organic)` — organic stickiness

**New columns added to `4-week Site - GA4`:**
- `Sum DAU (All)` — sum of daily all-channel active users
- `DAU/MAU % (All)` — all-channel stickiness (industry standard benchmark)
- `Sum DAU (Organic)` — sum of daily organic active users
- `DAU/MAU % (Organic)` — organic stickiness

**Interpretation:** DAU/WAU % above 100% means users average more than 1 visit per week. Typical content/video sites run 15–25%. Higher = more habitual return visits.

### Files Changed
- `scripts/weekly_site_ga4.py`
- `scripts/monthly_site_ga4.py`

---
<!-- Add new sessions below this line -->

## Session 7 — Data Accuracy & Highlighting Bug Fixes
**Date:** 2026-05-19

### Bug Fixed — Highlight Row Off-by-One (`sheets.py`)
**Root cause:** `batch_highlight()` passed `row_index` directly to the Google Sheets API, but the API uses 0-based row indexes while scripts calculated 1-based indexes. Every highlight landed one row above the intended cell, coloring the previous week's row instead of the current one.

**Fix:** Added `zero_based = row_index - 1` conversion inside `batch_highlight()` before passing to the API.

**Files changed:** `scripts/sheets.py`

---

### Bug Fixed — Wrong Page Dimension in GA4 Page Scripts
**Root cause:** `weekly_page_ga4.py` and `monthly_page_ga4.py` used `pagePath` as both the dimension and filter field. `pagePath` counts every page a user visits during a session, inflating metrics. The correct dimension is `landingPagePlusQueryString` which counts only sessions that started on that page.

**Symptom:** Script reported 1,296 all-channel sessions and 412 organic users for `/image-to-video-ai-free.html` vs GA4's correct 388 sessions and 65 organic users.

**Fix:** Replaced `pagePath` with `landingPagePlusQueryString` in all 4 places (top pages query, page filter, all-channel request, organic request). Filter match type changed from `EXACT` to `CONTAINS` to handle query string variants. Home page `/` uses `EXACT` to avoid matching all URLs.

**Files changed:** `scripts/weekly_page_ga4.py`, `scripts/monthly_page_ga4.py`

---

### Bug Fixed — Prev Data Read from Sheet Caused Wrong Change Values
**Root cause:** All page scripts read `prev` metrics from the sheet on subsequent runs. After fixing the `landingPagePlusQueryString` dimension, the sheet still contained old inflated `pagePath`-based numbers, causing change values like `-160` even though the current week's data was now correct.

**Fix:** All 5 page scripts now always fetch `prev` from the API for the prior period. The sheet is used only for `existing_row_count` to calculate the correct `row_index` for highlighting.

**Files changed:** `scripts/weekly_page_ga4.py`, `scripts/monthly_page_ga4.py`, `scripts/weekly_page_gsc.py`, `scripts/monthly_page_gsc.py`, `scripts/weekly_brand_gsc.py`

---

### Bug Fixed — Engagement Threshold Using Current Sessions Instead of Prev
**Root cause:** Both GA4 page scripts passed `metrics["org_sessions"]` (current week) as the `baseline_sessions` noise guard to the engagement threshold functions. Should be `prev["org_sessions"]` (prior week).

**Fix:** Added `org_sessions` to the `prev` dict and changed both calls to pass `prev["org_sessions"]`.

**Files changed:** `scripts/weekly_page_ga4.py`, `scripts/monthly_page_ga4.py`

---

### Bug Fixed — Engagement Threshold 100–499 Sessions Gap (`thresholds.py`)
**Root cause:** `weekly_page_engagement_ratio()` only alerted for `baseline_sessions >= 500`. Sessions 100–499 silently returned `None`.

**Fix:** Sessions 100–499 now alert Yellow only (≥ 12pp change, no Red). Sessions ≥ 500 unchanged (Red ≥ 12pp, Yellow ≥ 8pp).

**Files changed:** `scripts/thresholds.py`

---

### Bug Fixed — Cross-Subdomain URL Contamination in Page Scripts
**Root cause:** `manual_urls` was filtered with `info["lan"] == prop["lan"] or subdomain in url`, pulling in URLs from other subdomains sharing the same language tag.

**Fix:** All 4 page scripts now use `url.startswith(base_url)` for both `top_urls` and `manual_urls`.

**Files changed:** `scripts/weekly_page_ga4.py`, `scripts/monthly_page_ga4.py`, `scripts/weekly_page_gsc.py`, `scripts/monthly_page_gsc.py`

---

### Bug Fixed — Wrong GSC Property for www.vidmud.com (`config.py`)
**Root cause:** `config.py` had `"gsc": "sc-domain:vidmud.com"` for the EN/www property. The actual registered GSC property is `https://www.vidmud.com/`. This caused zero data returned for all www GSC queries.

**Fix:** Updated to `"gsc": "https://www.vidmud.com/"`.

**Files changed:** `scripts/config.py`

---

### Key Decisions Updated
- **Previous period comparison** — always fetched from API, never from sheet
- **Page dimension** — `landingPagePlusQueryString` with `CONTAINS` (except `/` uses `EXACT`)
- **URL filtering** — `url.startswith(base_url)` for strict subdomain isolation across all page scripts
