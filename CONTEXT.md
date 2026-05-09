# CONTEXT.md — SEO Data Automation for Vidmud

## What This Project Does
Automatically pulls GA4 and GSC data for all Vidmud subdomains, writes it to a Google Sheet,
and highlights cells that exceed alert thresholds (Yellow = warning, Red = critical).

## Architecture
- **Platform:** GitHub Actions (public repo, unlimited free minutes)
- **Data Sources:** Google Analytics 4 API + Google Search Console API
- **Output:** Google Sheets (one shared workbook)
- **Alerts:** Cell color highlighting only (Yellow / Red), no email
- **Auth:** Google Service Account (single JSON key covers both GA4 and GSC)

## Repo: SaraZhang919/data-automation-vm

## Google Sheet ID
`1i1UMr2xx_RnlD80a0gFR3h85oE4CzD87tKDU0o0eqKM`

## Properties (10 Subdomains)
| Language | Subdomain | GSC Property | GA4 Property ID |
|---|---|---|---|
| EN | www.vidmud.com | www.vidmud.com | 438691348 |
| DE | de.vidmud.com | https://de.vidmud.com | 459413242 |
| FR | fr.vidmud.com | https://fr.vidmud.com | 459379487 |
| ES | es.vidmud.com | https://es.vidmud.com | 459417270 |
| IT | it.vidmud.com | https://it.vidmud.com | 459369622 |
| JP | jp.vidmud.com | https://jp.vidmud.com | 459364055 |
| TW | tw.vidmud.com | https://tw.vidmud.com | 459389514 |
| AR | ar.vidmud.com | https://ar.vidmud.com | 459394157 |
| KR | kr.vidmud.com | https://kr.vidmud.com | 459392728 |
| PT | pt.vidmud.com | https://pt.vidmud.com | 459404147 |

## Sheet Structure (tabs in the Google Sheet)
| Tab Name | Data Source | Schedule |
|---|---|---|
| Page name - manual management | Manual | Never auto-written |
| Site Event Logs - Manual | Manual | Never auto-written |
| Weekly Site - GA4 | GA4 | Every Sunday 4PM JST |
| Weekly by page - GA4 | GA4 | Every Sunday 4PM JST |
| Weekly by page - GSC | GSC | Every Tuesday 4PM JST |
| Weekly brand by impressions | GSC | Every Tuesday 4PM JST |
| Daily | GA4 | Every day 4PM JST |
| 4-week Site - GA4 | GA4 | 4th of month 4PM JST |
| 4-week page - GA4 | GA4 | 4th of month 4PM JST |
| 4-week by page - GSC | GSC | 4th of month 4PM JST |
| Thresholds | Manual | Never auto-written |

## Schedules (all times JST = UTC+9, so 4PM JST = 07:00 UTC)
- Daily: `0 7 * * *`
- Weekly Sunday: `0 7 * * 0`
- Weekly Tuesday: `0 7 * * 2`
- Monthly 4th: `0 7 4 * *`

## Scripts
| File | Purpose |
|---|---|
| `scripts/config.py` | All property IDs, sheet names, subdomain list |
| `scripts/auth.py` | Google service account authentication |
| `scripts/sheets.py` | Sheet read/write + cell highlighting helpers |
| `scripts/thresholds.py` | Alert threshold logic (Yellow/Red) |
| `scripts/daily_ga4.py` | Daily GA4 by subdomain |
| `scripts/weekly_site_ga4.py` | Weekly GA4 site-level |
| `scripts/weekly_page_ga4.py` | Weekly GA4 by page |
| `scripts/weekly_page_gsc.py` | Weekly GSC by page |
| `scripts/weekly_brand_gsc.py` | Weekly brand queries GSC |
| `scripts/monthly_site_ga4.py` | Monthly GA4 site-level |
| `scripts/monthly_page_ga4.py` | Monthly GA4 by page |
| `scripts/monthly_page_gsc.py` | Monthly GSC by page |

## Key Decisions Made
1. **Service Account auth** (not OAuth) — no token expiry, no browser flow needed
2. **Public repo** — credentials are in GitHub Secrets, code has no sensitive data
3. **Previous week comparison** — first run pulls from API; subsequent runs read from sheet column
4. **Pages tracked** — top 30 by organic active users per subdomain + all URLs in "Page name" sheet, deduplicated
5. **Brand queries** — filter GSC for exact "Vidmud" + contains "Vidmud"; week-over-week from sheet
6. **Engagement metrics** (New Users, Engagement Rate, Avg Session Duration, Key Events) — filtered to Organic Search
7. **Alert levels** — Yellow and Red only, matching Thresholds sheet exactly
8. **All monthly jobs on 4th** — sequential, ~10-15 min total, well within free tier
9. **Manual trigger** — all workflows support `workflow_dispatch` with date override for testing
10. **No email notifications** — sheet highlighting is the only alert mechanism

## GitHub Secrets Required
| Secret Name | Value |
|---|---|
| `GOOGLE_CREDENTIALS` | Full contents of your service account JSON key |
| `SHEET_ID` | `1i1UMr2xx_RnlD80a0gFR3h85oE4CzD87tKDU0o0eqKM` |

## Where to Manage Credentials
- Go to your repo → **Settings** → **Secrets and variables** → **Actions**
- Click **New repository secret**
- Add `GOOGLE_CREDENTIALS` (paste entire JSON content)
- Add `SHEET_ID` (paste the sheet ID string)
- **Never** put credentials in any script file or commit them to the repo

## Testing Without Waiting for Schedule
Every workflow supports manual trigger with a custom date:
1. Go to GitHub → Actions → select any workflow
2. Click **Run workflow**
3. Enter a past date (e.g. a past Sunday for weekly jobs)
4. Click Run — it executes immediately with real data
