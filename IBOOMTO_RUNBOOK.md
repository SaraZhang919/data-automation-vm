# iBoomto monitoring

Cloud entrypoint: **Actions → iBoomto Monitor**. Data collection and calculations use Python; only report interpretation uses the OpenAI API.

Deployment (2026-09-09): implemented on main. Fourteen unit tests, a local complete run including the first GPT-5.6 Sol report, both cloud manual-source checks, and a complete cloud run passed. Full cloud validation run 34322957257 completed in about 3m34s with the issued report cached. Scheduled triggers are configured below. OpenAI credential transfer to GitHub is awaiting explicit user authorization; until configured, new reports retain factual metrics and show AI failure. Clarity and website logs remain not configured. Business event mappings require tracking-trigger verification.

## Outputs

- [IBT - Website Data](https://docs.google.com/spreadsheets/d/1Iw07GRTmwK4GoE3zPpGYG-rdneBHchYIb6-s-knFLvs/edit): source data, configurations, ingestion state, revisions, technical snapshots, period statistics, and manual results. `Properties` is read-only to the monitor.
- [iBoomto — Daily Report](https://docs.google.com/spreadsheets/d/15jBCSt2FqujGjm-L8-PFZTpkMCSDtJVKDl1rEANNNKU/edit): latest report, immutable issued reports, issues, source status, deep analysis and API usage.
- [Screaming Frog upload folder](https://drive.google.com/drive/folders/1QKOgh4aFtVM1CQqaqdwlVSklq8s4LiND): dated YYYYMMDD folders containing internal_all.csv, inlinks.csv, hreflang_all.csv.

## Approved schedule (Asia/Tokyo)

| Task | Trigger | Data period |
|---|---|---|
| Daily GA/GSC, technical checks and report | Every day 17:00 | Previous seven closed dates in the source timezone; GA provisional and GSC final/provisional separately labelled |
| GA weekly preview | Sunday 20:00 | Previous Sunday–Saturday |
| GA weekly revision and GSC weekly pull | Tuesday daily run at 17:00 | Same full Sunday–Saturday interval; pending periods retry on following daily runs |
| GA/GSC calendar month | Fourth of each month 16:00 | Previous calendar month; independent source status and pending retries |

GitHub scheduling is best effort and may queue. Reports follow collectors, not a separate racing timer. 17:15–17:30 is a target to verify against actual runs, not a guaranteed completion time. Index checks use four workers with bounded request timeouts and rotate 30 URLs per day by default (configurable ceiling 100), starting with homepages and new URLs. GA date boundaries come from GA Data API metadata; GSC uses America/Los_Angeles. No source is assumed to use the runner's JST day.

GA mature means 48 hours after the source calendar day closed; this is an operational rule, not a platform guarantee. GSC `final` publication evidence controls comparisons. Missing data is never imputed as zero. The first launch week/month is labelled partial and not compared normally. Launch date: 2026-09-07.

## Credentials

Existing `GOOGLE_CREDENTIALS` is reused. It must identify gsc-api-service@gsc-api-project-453403.iam.gserviceaccount.com. GA/GSC read permission and write access to the two workbooks are needed. Drive API must be enabled for the project, with read access to the SF folder. Admin API is not required.

`OPENAI_API_KEY` powers GPT-5.6 Sol (`medium` daily, `high` deep). No silent fallback model. `CLARITY_API_TOKEN` is optional until supplied. Store credentials only in Actions Secrets; do not commit keys or raw private exports. Old `SHEET_ID` is deliberately unused by iBoomto, so Vidmud's historical target is not changed.

The monitor scopes Google API access to analytics.readonly, webmasters.readonly, spreadsheets, drive.readonly. It does not require project Owner or cloud-platform for routine operation. One-time API enablement is separate from scheduled code.

## Manual use

- Custom date query: select mode `manual`, source, start/end (inclusive), language and optionally exact URL/path prefix. The matching equal-length baseline is queried too. Results go to `Manual Results`; daily tables are not overwritten. The legacy Manual Check and Manual Page Detail workflow entrypoints now invoke this iBoomto collector.
- Deep analysis: select mode `deep`, enter a question or issue ID, with optional dates/language/URL/prefix. It reads stored evidence, explicitly states unavailable dates, and stores its answer in `Deep Analysis`.
- Backfill more than seven days: mode `daily`, source `ga` or `gsc`, specify start/end. It updates source rows. Issued daily reports remain unchanged unless `force` is explicitly selected.
- Regenerate a report: `force=true` is an explicit additional API invocation. There is no arbitrary LLM spending quota; usage is recorded.

## Human-maintained inputs

- `Event Mapping`: one business action and language per row; comma-separated exact event names and `confirmed=true` after verifying the tracking trigger. Multiple events for one action are queried together to deduplicate converters. `Event Candidates` is discovery only. Do not confuse converted-file downloads with Windows software download or installation success.
- `Priority Pages`: add URLs and enabled flags. Language homepages are included by default.
- `Page Map`: optional page types and equivalent groups; translated slugs need not match. `zh-tw` corresponds to hreflang `zh-Hant`; x-default is not a tenth locale.
- `Thresholds`: versioned count and ratio rules. Low-volume or provisional data cannot trigger ordinary drop alerts. Review actual historical revisions after 2–4 weeks before changing the seven-day backfill.
- SF: upload Tuesday/Friday in the first month, weekly Tuesday afterwards and after major releases. Import is automatic; running the desktop crawl is still manual. Files have to be complete and unchanged during import.

## Failure and retention behavior

Sources fail independently, with safe error types in `Run Status`. Partial/stale/unconfigured states are distinct from zero and success. AI failure leaves a factual report. An already issued successful report is not silently overwritten by a backfill. Failed AI reports may be retried.

Data revisions are retained. Latest links/hreflang have dedicated current views, while page snapshots and raw Drive batches provide history. Raw SF files are currently retained without automatic deletion; a 90-day cleanup policy must preserve at least three successful batches and all failed/unprocessed batches before deletion is enabled.

Website access logs are a later integration once the tech team supplies an archive location/format; installer logs are explicitly excluded. Until then `Website logs` is marked not configured. Clarity collects overall/URL/device rolling 24h views, does not add overlapping windows, and observes the provider's 10 requests/day and non-paginated 1,000-row ceiling.

## Validation

`python -m unittest discover -s tests -v` covers language boundaries, launch/calendar cutoffs, source timezones, whole-period users, idempotent writes, API failure preservation, malformed CSV, partial sitemap, issue resolution, provisional alert gating, RAW Sheets writes and AI fallback/immutable reports.

`python -m iboomto.preflight --env-file ../.env.local` checks live read access and model availability. For an isolated collector run without remote writes: `python -m iboomto.run --env-file ../.env.local --no-ai`. Only `--write` enables Sheets changes. Private diagnostics are written under ignored runtime/.
