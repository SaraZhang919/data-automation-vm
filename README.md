# Vidmud SEO Data Automation

Automatically pulls GA4 + GSC data for all Vidmud subdomains, writes to Google Sheets, and highlights alert thresholds.

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

> The first run will write headers automatically. Manual tabs stay untouched.

---

## Testing (Without Waiting for Schedule)

Every workflow can be triggered manually with a custom date:

1. Go to **Actions** tab in GitHub
2. Select a workflow (e.g. "Weekly Sunday")
3. Click **Run workflow**
4. Enter a past date (e.g. `2026-04-27` for a past Sunday)
5. Click **Run workflow**

The job runs immediately and writes real data to your sheet.

**Good test dates to use:**
- Daily: any past date e.g. `2026-05-01`
- Weekly Sunday: `2026-04-27`
- Weekly Tuesday: `2026-04-29`
- Monthly: `2026-05-04` (will pull April data)

---

## Schedules

| Workflow | Cron | JST Time | Covers |
|---|---|---|---|
| Daily GA4 | `0 7 * * *` | 4PM daily | Yesterday |
| Weekly Sunday | `0 7 * * 0` | 4PM Sunday | Last Sun–Sat |
| Weekly Tuesday | `0 7 * * 2` | 4PM Tuesday | Last Sun–Sat |
| Monthly | `0 7 4 * *` | 4PM on 4th | Previous month |

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
│   └── monthly.yml
├── scripts/
│   ├── config.py          ← Properties, sheet names, constants
│   ├── auth.py            ← Service account auth
│   ├── sheets.py          ← Read/write/highlight helpers
│   ├── thresholds.py      ← Yellow/Red alert logic
│   ├── daily_ga4.py
│   ├── weekly_site_ga4.py
│   ├── weekly_page_ga4.py
│   ├── weekly_page_gsc.py
│   ├── weekly_brand_gsc.py
│   ├── monthly_site_ga4.py
│   ├── monthly_page_ga4.py
│   └── monthly_page_gsc.py
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
