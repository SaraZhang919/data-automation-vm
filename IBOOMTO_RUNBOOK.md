# iBoomto monitoring — v2

Approved migration: 2026-09-09. Source data and Google Sheets calculations use Python. Only analysis uses the existing OpenAI API. No key values appear in this repository.

## Outputs

- [IBT - Website Data](https://docs.google.com/spreadsheets/d/1Iw07GRTmwK4GoE3zPpGYG-rdneBHchYIb6-s-knFLvs/edit)
- [使用指南 Guide](https://docs.google.com/spreadsheets/d/1Iw07GRTmwK4GoE3zPpGYG-rdneBHchYIb6-s-knFLvs/edit#gid=1208128487): user-owned descriptions, definitions, scopes, schedules and tab links. Routine jobs preserve this guide; explicit documentation edits are applied only to selected cells.
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

GitHub scheduling may queue. Reports run after collection. GA maturity means 48 hours after period close, not a provider guarantee. GSC uses final publication metadata, accepting both firstIncompleteDate and first_incomplete_date. Daily GSC acquisition ends at the confirmed completed date and uses dataState=final for site, page and query metrics. The all-state date probe is used only to discover the publication boundary. If no launch-day final data is available, the run reports waiting_for_final_data. Historical preview rows remain stored but cannot drive current reports, comparisons or deep analysis. First launch week/month are partial. Weekly/monthly users come from whole-period API queries, never daily sums.

## Tables and selection

GA4 Site / GSC Site replace the former Daily tab titles, preserving their sheet IDs. Same-type rows share a sheet with period, start, end. GA channels, landing pages, events and GSC pages/queries expose plain dimensions; page fields include subfolder, page_type, page_name, page_url. Unknown manual metadata remains empty. CTR and conversion rates are numeric percentages; change_pp is percentage points. key_events_per_user is not CTR.

Page name - manual management is the only page registry. Properties, the page registry and Site Event Logs - Manual are read-only to the program. Supported path prefixes: ar, ja, zh-tw, es, de, fr, it, pt; unprefixed paths of any depth are English. JP/TW labels map to ja/zh-tw. Incorrect double slashes are flagged, not silently rewritten.

Per-language daily page pool: GA organic active users Top30, GSC clicks Top30, plus every valid manual URL. Weekly/monthly pools include the previous period Top30. Exact page queries prevent substring collisions. Missing selected-page responses display n.a. with no_data_returned. GSC query selection uses the bounded opportunity union documented below; never represented as exhaustive.

Event Mapping contains only software_download. Semantic confirmation is distinct from actual tracking verification. Each property must emit/create that event; marking a name as a key event alone does not convert dl_* events or backfill history. Counts describe download clicks, not completed downloads or installs. GA4 Business Events calculates full-period deduplicated trigger users and user conversion rate. No rows means waiting_for_event_data, not proven zero.

## Reports and comparisons

Overview, Weekly Overview and Monthly Overview update independently. Report History preserves issued versions; changed evidence generates a revision. Cached AI text never prevents current facts from refreshing. The report includes period-matched business-event metrics, channels/pages/query summaries, comparisons and technical issues. P1 is critical-page/core-collection failure; P2 is a local SEO issue or adequately supported mature-metric anomaly; P3 is observation/opportunity. LLM explains evidence and priority, not invented causality.

Comparisons exists immediately, with unavailable reasons until a compatible baseline exists. Day-over-day and same-weekday gates are independent. Missing data is not zero; zero baselines are new_activity. First full week is September 13–19; two full weeks finish September 26. September is a partial launch month.

## Storage and credentials

Hidden columns/tabs remain readable and writable. Do not rename dependencies or headers. Writes update only changed rows and preserve hidden-column preferences through header migration. Use filter views and keep manual notes outside generated rows.

Main-sheet retention: daily detail 90 days, site daily 365 days, weekly 104 weeks, monthly 36 months. Archive Config points to a pre-provisioned human-owned private gzip file. The archive is written and downloaded for checksum verification before old source rows are removed. Missing or failed archives never delete data. Storage Status records outcomes. Raw SF files stay in Drive; Sheets keep compact current summaries and problem evidence. Sitemap current state is refreshed; history logs differences only, and partial fetch failures cannot create removal events.

GOOGLE_CREDENTIALS remains the existing service-account JSON in GitHub Actions Secrets; OPENAI_API_KEY remains the existing OpenAI secret. Routine scopes are analytics.readonly, webmasters.readonly, spreadsheets, drive.readonly. Only the archive path requests the Drive scope needed to update the specified existing private file; its service-account ACLs still govern access. No project Owner or cloud-platform role is required. CLARITY_API_TOKEN is optional; website access logs remain a later integration and installer logs are excluded.

The owner authorized the expanded analysis evidence transfer to OpenAI. IBOOMTO_AI_REPORTS_ENABLED=true enables it; the switch can still pause analysis without pausing collection. The existing synthetic connection test is separate.

Model: gpt-5.6-sol, medium for daily/weekly/monthly, high for deep. Requested and actual response model, usage, prompt version and rule version are recorded. No silent model fallback. All API calls use fixed provider HTTPS endpoints and errors do not echo secrets. Actions run only on main, official actions are SHA-pinned, and checkout does not persist credentials.

## Manual operations

Actions → iBoomto Monitor: manual mode requires start/end, source, language, optional exact URL/prefix; results go to Manual Results. Deep mode accepts a question and stored-data selection. Daily mode with dates backfills source partitions and creates a report revision if evidence changes. force=true explicitly requests another AI generation. Weekly and monthly data are queried over their entire intervals.

## Verification and rollback

Run `python -m unittest discover -s tests -v`. Tests cover source timezone boundaries, exact host scope, mandatory manual pages, missing vs zero, GSC camelCase publication metadata, full-period users, report isolation/revisions, and fail-closed retention.

One-time migration uses iboomto.backup and iboomto.migrate_v2. Verified full-grid backups include formulas, formats, metadata and values for both workbooks; they live under ignored outputs, never in the public repository. Retired tabs are removed only after a successful compact import and data verification. Use iboomto.setup_archive to verify a human-owned private archive before retention starts.


## Compact LLM evidence and Clarity every 48 hours

The LLM receives a separate columnar analytical view, not the full workbook or raw server logs. Repeated storage fields and URLs with query strings are removed; unavailable comparison rows are grouped by reason and period while preserving counts, metrics and languages. Selected GA/GSC page/query aggregate values, source quality, dates and every issue remain available. Deep mode reads explicitly selected historical aggregates. Oversized evidence is partitioned across nested dictionaries/tables without dropping sections. No new token spending cap is imposed.

AI Usage exposes provider-reported input_tokens, output_tokens, total_tokens and reasoning_tokens (a subset of output), plus input_characters and evidence_schema. Character reduction is not an exact token/cost estimate. Cache keys use the compact evidence, model, prompt/rule versions and question.

Clarity uses fixed 48-hour slots anchored at 2026-09-10 17:00 JST (08:00 UTC). The daily workflow collects due slots; subsequent calls in a completed slot skip HTTP. Normal dates are September 10, 12, 14, etc.; month boundaries do not reset the cadence. Failed views can retry on the next run, at most three attempts per view/slot and ten recorded project requests per UTC day. Other clients share the provider's quota. GitHub queue delays can shift actual collection times.

Each batch normally makes two requests with numOfDays=3: an overall request stored in Clarity Snapshots, and dimension1=URL filtered locally into Clarity Pages. Select up to 20 positive-click pages globally across all languages, from a direct GSC final-only page query on www.iboomto.com over the latest seven completed GSC dates (truncated at launch). This page watchlist is independent of the expanded GSC Queries rule below. Each page row records its GSC selection dates separately from its actual rolling 72-hour Clarity window. Clarity behavior includes all traffic channels, not just organic search.

The API has no documented URL filter and returns at most 1,000 rows without pagination. Thus Top20 bounds stored/analyzed results, not provider coverage. Missing URLs are labelled not_returned with unknown metrics, never zero. Multiple query-string variants matching a page are marked ambiguous rather than summing unique users or rates. Page snapshots have a 90-day retention target; deletion requires successful private archive verification. No archive means rows remain, with Storage Status reporting the need for configuration.

Daily/weekly/monthly LLM evidence contains only the latest overall snapshot and latest page batch (at most 20 rows), not the complete API response or Clarity history. Overlapping windows must never be summed into week/month totals. Legacy 24-hour snapshots retain their original labels. Metrics include traffic, dead/rage/error clicks, script errors, scroll depth and engagement time. Overall project totals may include other hosts and must not be equated with production-filtered GA totals. GA and Clarity patterns are supporting evidence, not user-level attribution or proven causation.

Reference: https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-data-export-api

Actions mode report-only regenerates analysis from existing stored facts without rerunning source APIs. It is suitable after enabling LLM or refining report formatting.
# Workbook preservation update — 2026-09-10

- Existing Guide tabs are user-owned, including case variants such as `使用指南guide`. Scheduled jobs never rebuild them. Edit specific guide cells only for an explicit documentation update, preserving notes and layout.
- Existing data tabs retain their current column order, widths, row heights, hidden state, frozen panes and number formats. Routine writes update values; new fields append, and new rows inherit the preceding data row's format. Automated result rows are still refreshed by their data partition; use the manual guide/register for annotations.
- `subfolder` is omitted from GA4 Landing Pages and GSC Pages. Other page metadata and the collection scope remain unchanged.
- Count metrics use integer display (`#,##0`); engagement rate and CTR remain percentages. `averageSessionDuration` remains seconds, and position retains decimals.
- Landing-page selection ranks `activeUsers` under **session** Organic Search, then requests **all-channel** metrics for the selected pages. No First user channel filter is applied.
- Daily query ranking requests one day with the `query` dimension alone; the known date is attached locally. The approved candidate expansion is now enabled as documented below.
- The event collection cadence and seven-day GA/GSC backfill remain unchanged. The subsequently approved Clarity 48-hour/Top20 update is documented above; other evidence-scope proposals remain unimplemented.


## Missing-value display and GSC query opportunities (2026-09-10)

Automated GA/GSC/Clarity metric cells and unmapped page_name/page_type cells display n.a. when missing or inapplicable. Real zeros remain numeric zeros. The Sheets reader converts these supported n.a. fields back to missing values before analytics and LLM evidence preparation. Identifiers, dimensions, configuration, manual source tables and user-added columns are not filled. Existing eligible data cells received the same display treatment; user styles and notes are preserved.

GSC Queries requests up to 5,000 query rows per language/date or full week/month with dataState=final, then saves the deduplicated union of clicks Top100, impressions Top100, up to 50 new candidates and up to 50 growing candidates (at most 300 rows). The raw candidate pools stay in memory and are not sent to the LLM. API ordering is by clicks, so the impressions ranking is within this candidate pool, not a guaranteed global impressions Top100. Anonymous queries and provider-internal limits remain absent even if fewer than 5,000 rows return. candidate_pool_truncated marks a full response or a provider cap.

Daily candidates compare with the preceding seven full post-launch days; weekly candidates compare with the preceding equal-length period; monthly candidates compare with the previous calendar month. Partial pre-launch baselines or no returned baseline queries disable new/growth labels, with baseline_status explaining why. New candidates mean absent from the baseline pool and at least 10 impressions/day in the current period, ranked by impressions; this is not a claim of first-ever appearance. Missing baseline values are n.a., never zero. Growth candidates must be present in both pools, with at least 20 impressions/day now, at least 10 additional impressions/day, and at least 50% growth in daily-average impressions. Rank growth candidates by absolute daily increase. This normalization handles different month lengths and daily versus seven-day baselines. These are observation filters, not alert thresholds or proof of SEO impact.

selection_reason preserves all matching categories with | separators. Baseline dates, counts, daily deltas, growth ratio, pool coverage and rule version are recorded. Current metrics remain exact API period metrics; do not sum selected queries to reproduce site totals. No manual keyword watchlist is implemented. Existing LLM reports consume the latest selected query union, not all 5,000 candidates, so tokens may rise with the number of selected rows; selection itself uses no LLM. Historical AI text is not automatically regenerated for this migration.
