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
