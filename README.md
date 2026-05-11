# Vidmud SEO Data Automation

Automatically pulls GA4 + GSC data for all Vidmud subdomains, writes to Google Sheets, and highlights alert thresholds.
Also supports manual ad-hoc checks by date range and by page name with daily breakdown.

---

## Quick Links
- **Google Sheet:** https://docs.google.com/spreadsheets/d/1i1UMr2xx_RnlD80a0gFR3h85oE4CzD87tKDU0o0eqKM
- **Context & Architecture:** [CONTEXT.md](./CONTEXT.md)
- **Change History:** [CHANGELOG.md](./CHANGELOG.md)

---

## One-Time Setup

### Step 1 — Grant Service Account Access to GA4

Do this for **all 10 GA4 properties**:
1. Go to [analytics.google.com](https://analytics.google.com)
2. Admin → Account Access Management (or Property Access Management)
3. Click `+` → Add users
4. Email: `gsc-api-service@gsc-api-project-453403.iam.gserviceaccount.com`
5. Role: **Viewer**
6. Repeat for all 10 properties

### Step 2 — Grant Service Account Access to GSC

Do this **once** (covers all properties you own):
1. Go to [search.google.com/search-console](https://search.google.com/search-console)
2. For each property: Settings → Users and permissions → Add user
3. Email: `gsc-api-service@gsc-api-project-453403.iam.gserviceaccount.com`
4. Permission: **Full**

### Step 3 — Enable APIs in Google Cloud

Go to [console.cloud.google.com](https://console.cloud.google.com) → project `gsc-api-project-453403`:
1. APIs & Services → Enable APIs
2. Enable: **Google Analytics Data API**
3. Enable: **Google Search Console API**
4. Enable: **Google Sheets API**

### Step 4 — Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret Name | Value |
|---|---|
| `GOOGLE_CREDENTIALS` | Paste the **entire contents** of your service account JSON file |
| `SHEET_ID` | `1i1UMr2xx_RnlD80a0gFR3h85oE4CzD87tKDU0o0eqKM` |

> ⚠️ Never put credentials in any script file. GitHub Secrets is the only safe place.

### Step 5 — Create Sheet Tabs

In your Google Sheet, create these tabs with these **exact names**:
- `Page name - manual management`
- `Site Event Logs-Manual`
- `Weekly Site - GA4`
- `Weekly by page - GA4`
- `Weekly by page - GSC`
- `Weekly brand by impressions`
- `Daily`
- `4-week Site - GA4`
- `4-week page - GA4`
- `4-week by page - GSC`
- `Thresholds`
- `Manual check - GA4`
- `Manual check - GSC`
- `Manual page detail - GA4`
- `Manual page detail - GSC`

> The first run will write headers automatically. Manual tabs stay untouched.

---

## Scheduled Workflows

| Workflow | Cron | JST Time | Covers |
|---|---|---|---|
| Daily GA4 | `0 7 * * *` | 4PM daily | Yesterday |
| Weekly Sunday | `0 7 * * 0` | 4PM Sunday | Last Sun–Sat |
| Weekly Tuesday | `0 7 * * 2` | 4PM Tuesday | Last Sun–Sat |
| Monthly | `0 7 4 * *` | 4PM on 4th | Previous month |

---

## Manual Workflows

### Manual Check
Run GA4 or GSC by-page data for any custom date range.
Comparison period is automatically the same-length period immediately before your chosen range.

1. Go to **Actions** → **Manual Check** → **Run workflow**
2. Enter `start_date` and `end_date` *(start must be before end)*
3. Choose `both`, `ga4_only`, or `gsc_only`
4. Results append to `Manual check - GA4` and/or `Manual check - GSC` tabs

### Manual Page Detail
Run a daily breakdown + summary for a specific page name across all subdomains.

1. Go to **Actions** → **Manual Page Detail** → **Run workflow**
2. Enter `start_date` and `end_date`
3. Enter `page_name` — must match what's in the `Page name - manual management` sheet. Supports pipe-separated values for multiple pages (e.g. `Home` or `Home|Online Tool`)
4. Optionally enter a `url_filter` to narrow results by URL substring. Supports pipe-separated values (e.g. `/home` or `/home|/tool`)
5. Choose `both`, `ga4_only`, or `gsc_only`
6. Results append to `Manual page detail - GA4` and/or `Manual page detail - GSC` tabs

**Output format per URL:**
```
Daily    2026-05-01   EN   www.vidmud.com   Home   https://...   metrics...
Daily    2026-05-02   EN   www.vidmud.com   Home   https://...   metrics...
...
Summary  2026-05-01 to 2026-05-07   EN   www.vidmud.com   Home   https://...   totals...
[blank row]
Daily    2026-05-01   DE   de.vidmud.com   Home   https://...   metrics...
```

---

## Testing Scheduled Workflows

Every scheduled workflow can be triggered manually with a custom date:

1. Go to **Actions** tab in GitHub
2. Select a workflow (e.g. "Weekly Sunday")
3. Click **Run workflow**
4. Enter a past date and click **Run workflow**

**Good test dates:**
| Workflow | Test Date |
|---|---|
| Daily | `2026-05-08` |
| Weekly Sunday | `2026-05-03` |
| Weekly Tuesday | `2026-05-06` |
| Monthly | `2026-05-04` |

---

## Alert Colors

| Color | Meaning |
|---|---|
| 🟡 Yellow | Warning — notable change, watch closely |
| 🔴 Red | Critical — significant drop or spike |

Thresholds are defined in the `Thresholds` sheet tab and coded in `scripts/thresholds.py`.

---

## File Structure

```
/
├── .github/workflows/
│   ├── daily.yml
│   ├── weekly_sunday.yml
│   ├── weekly_tuesday.yml
│   ├── monthly.yml
│   ├── manual_check.yml
│   └── manual_page_detail.yml
├── scripts/
│   ├── config.py                  ← Properties, sheet names, constants
│   ├── auth.py                    ← Service account auth
│   ├── sheets.py                  ← Read/write/highlight helpers
│   ├── thresholds.py              ← Yellow/Red alert logic
│   ├── daily_ga4.py
│   ├── weekly_site_ga4.py
│   ├── weekly_page_ga4.py
│   ├── weekly_page_gsc.py
│   ├── weekly_brand_gsc.py
│   ├── monthly_site_ga4.py
│   ├── monthly_page_ga4.py
│   ├── monthly_page_gsc.py
│   ├── manual_check_ga4.py        ← Manual check by date range
│   ├── manual_check_gsc.py        ← Manual check by date range
│   ├── manual_page_detail_ga4.py  ← Daily breakdown by page name
│   └── manual_page_detail_gsc.py  ← Daily breakdown by page name
├── requirements.txt
├── .gitignore
├── CONTEXT.md
├── CHANGELOG.md
└── README.md
```

---

## Adding a New Subdomain

Edit `scripts/config.py` → `PROPERTIES` list. Add one entry:
```python
{"lan": "XX", "subdomain": "xx.vidmud.com", "gsc": "https://xx.vidmud.com/", "ga4": "XXXXXXXXX"},
```
Then grant the service account access to that GA4 property and GSC property. No other changes needed.
