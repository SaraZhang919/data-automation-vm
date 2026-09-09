# iBoomto monitoring — v2

Approved migration: 2026-09-09. Source data and Google Sheets calculations use Python. Only analysis uses the existing OpenAI API. No key values appear in this repository.

## Outputs

- [IBT - Website Data](https://docs.google.com/spreadsheets/d/1Iw07GRTmwK4GoE3zPpGYG-rdneBHchYIb6-s-knFLvs/edit)
- [使用指南 Guide](https://docs.google.com/spreadsheets/d/1Iw07GRTmwK4GoE3zPpGYG-rdneBHchYIb6-s-knFLvs/edit#gid=1208128487): automatically refreshed descriptions, definitions, scopes, schedules and current tab links.
- [Daily / Weekly / Monthly Reports](https://docs.google.com/spreadsheets/d/15jBCSt2FqujGjm-L8-PFZTpkMCSDtJVKDl1rEANNNKU/edit)
- [Screaming Frog raw uploads](https://drive.google.com/drive/folders/1QKOgh4aFtVM1CQqaqdwlVSklq8s4LiND): YYYYMMDD subfolders with internal_all.csv, inlinks.csv, hreflang_all.csv. Running the desktop crawl remains manual.

## GA reconciliation — production hostname retained

Every GA collector uses `hostName` **EXACT** `www.iboomto.com`. It does not include all subdomains and does not use CONTAINS. Everything else is excluded: test subdomains, management/backend subdomains, localhost, LAN hostnames/IPs, the bare domain `iboomto.com`, and missing/not-set hostname values. This rule also excludes newly introduced test hosts automatically.

To reproduce a result in GA, choose the same language property, use the same source-calendar dates, add Host name exactly equal to www.iboomto.com, and select the same metric. Channels use **Session default channel group**, not First user default channel group. Language denotes the independent property; path language is exposed separately on page records. Data dates follow the GA property timezone (currently America/Los_Angeles), not the JST job date.


## Schedule (Asia/Tokyo)

| Job | Trigger | Source interval |
|---|---|---|
| Daily collection and report | 17:00 daily | Latest seven closed source-calendar days, clamped to launch |
| GA weekly preview | Sunday 20:00 | Previous Sunday–Saturday |
| GA revision + GSC weekly report | Tuesday 17:00, then pending retries | Same weekly period, sources independently marked |
| Calendar month report | Fourth day 16:00 | Previous natural month, with pending daily retries |

GitHub scheduling may queue. Reports run after collection. GA maturity means 48 hours after period close, not a provider guarantee. GSC uses final publication metadata, accepting both firstIncompleteDate and first_incomplete_date; all-state preview rows are visibly provisional. First launch week/month are partial. Weekly/monthly users come from whole-period API queries, never daily sums.

## Tables and selection

GA4 Site / GSC Site replace the former Daily tab titles, preserving their sheet IDs. Same-type rows share a sheet with period, start, end. GA channels, landing pages, events and GSC pages/queries expose plain dimensions; page fields include subfolder, page_type, page_name, page_url. Unknown manual metadata remains empty. CTR and conversion rates are numeric percentages; change_pp is percentage points. key_events_per_user is not CTR.

Page name - manual management is the only page registry. Properties, the page registry and Site Event Logs - Manual are read-only to the program. Supported path prefixes: ar, ja, zh-tw, es, de, fr, it, pt; unprefixed paths of any depth are English. JP/TW labels map to ja/zh-tw. Incorrect double slashes are flagged, not silently rewritten.

Per-language daily page pool: GA organic active users Top30, GSC clicks Top30, plus every valid manual URL. Weekly/monthly pools include the previous period Top30. Exact page queries prevent substring collisions. Missing selected-page responses have blank metrics and no_data_returned. GSC query selection is Top100 clicks per language/day or whole period; never represented as exhaustive.

Event Mapping contains only software_download. Semantic confirmation is distinct from actual tracking verification. Each property must emit/create that event; marking a name as a key event alone does not convert dl_* events or backfill history. Counts describe download clicks, not completed downloads or installs. GA4 Business Events calculates full-period deduplicated trigger users and user conversion rate. No rows means waiting_for_event_data, not proven zero.

## Reports and comparisons

Overview, Weekly Overview and Monthly Overview update independently. Report History preserves issued versions; changed evidence generates a revision. Cached AI text never prevents current facts from refreshing. The report includes period-matched business-event metrics, channels/pages/query summaries, comparisons and technical issues. P1 is critical-page/core-collection failure; P2 is a local SEO issue or adequately supported mature-metric anomaly; P3 is observation/opportunity. LLM explains evidence and priority, not invented causality.

Comparisons exists immediately, with unavailable reasons until a compatible baseline exists. Day-over-day and same-weekday gates are independent. Missing data is not zero; zero baselines are new_activity. First full week is September 13–19; two full weeks finish September 26. September is a partial launch month.

## Storage and credentials

Hidden columns/tabs remain readable and writable. Do not rename dependencies or headers. Writes update only changed rows and preserve hidden-column preferences through header migration. Use filter views and keep manual notes outside generated rows.

Main-sheet retention: daily detail 90 days, site daily 365 days, weekly 104 weeks, monthly 36 months. Archive Config points to a pre-provisioned human-owned private gzip file. The archive is written and downloaded for checksum verification before old source rows are removed. Missing or failed archives never delete data. Storage Status records outcomes. Raw SF files stay in Drive; Sheets keep compact current summaries and problem evidence. Sitemap current state is refreshed; history logs differences only, and partial fetch failures cannot create removal events.

GOOGLE_CREDENTIALS remains the existing service-account JSON in GitHub Actions Secrets; OPENAI_API_KEY remains the existing OpenAI secret. Routine scopes are analytics.readonly, webmasters.readonly, spreadsheets, drive.readonly. Only the archive path requests the Drive scope needed to update the specified existing private file; its service-account ACLs still govern access. No project Owner or cloud-platform role is required. CLARITY_API_TOKEN is optional; website access logs remain a later integration and installer logs are excluded.

Model: gpt-5.6-sol, medium for daily/weekly/monthly, high for deep. Requested and actual response model, usage, prompt version and rule version are recorded. No silent model fallback. All API calls use fixed provider HTTPS endpoints and errors do not echo secrets. Actions run only on main, official actions are SHA-pinned, and checkout does not persist credentials.

## Manual operations

Actions → iBoomto Monitor: manual mode requires start/end, source, language, optional exact URL/prefix; results go to Manual Results. Deep mode accepts a question and stored-data selection. Daily mode with dates backfills source partitions and creates a report revision if evidence changes. force=true explicitly requests another AI generation. Weekly and monthly data are queried over their entire intervals.

## Verification and rollback

Run `python -m unittest discover -s tests -v`. Tests cover source timezone boundaries, exact host scope, mandatory manual pages, missing vs zero, GSC camelCase publication metadata, full-period users, report isolation/revisions, and fail-closed retention.

One-time migration uses iboomto.backup and iboomto.migrate_v2. Verified full-grid backups include formulas, formats, metadata and values for both workbooks; they live under ignored outputs, never in the public repository. Retired tabs are removed only after a successful compact import and data verification. Use iboomto.setup_archive to verify a human-owned private archive before retention starts.
