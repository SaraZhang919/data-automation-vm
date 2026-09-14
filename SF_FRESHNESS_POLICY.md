# Screaming Frog freshness for routine reports

The automation imports manual CSV exports; it does not launch the SF crawler.
Previously, identical batches were skipped, but older unimported batches could
still be downloaded and parsed. SEO comparisons reused the latest successful
snapshot indefinitely; LLM evidence included the last three import records and
unresolved SF issues without a freshness gate. The old 4/7-day age label did not
actually exclude those findings from reports.

The new rule applies to daily, weekly and monthly reports:

- Only the current JST calendar day's crawl is eligible. Old/future/invalid
  dated folders are skipped before listing their files or downloading CSVs.
- Already imported identical batch IDs are skipped. Identical CSV bytes under
  changed metadata/new folders are also rejected after content verification.
- Every nonempty Crawl Timestamp must parse and belong to today. Upload time
  does not refresh crawl time. Without Crawl Timestamp, YYYYMMDD folder naming
  is the fallback: it must name the actual crawl date, not the upload date.
- A newly validated batch receives freshness_policy=same-jst-day-v1. Legacy
  unverified snapshots are retained, but excluded from current SF evidence.
- Stale SF does not generate new link/comparison findings or seed extra HTTP
  check candidates. Independently selected pages still receive live checks.
- Report payloads exclude old SF batch records and SF issues whose provenance
  does not match a fresh validated batch. Only an availability status remains.
  Old issues are not automatically declared resolved. No-fresh-data is not health.
- A fresh same-day snapshot may support that day's daily/weekly/monthly reports,
  with its date, but is not presented as a week/month of observations.
- Existing Drive CSVs, Sheet snapshots and historical reports are not deleted
  or rewritten. Upload a new crawl to its correctly dated YYYYMMDD folder to
  resume SF input. Weekly/monthly runs without a fresh import omit SF evidence.

This is a programmatic filter; it makes no new LLM calls and does not re-run
historical reports. Rules live in iboomto/sf_freshness.py. Tests cover date
boundaries, old-folder skips, old crawls re-uploaded today, repeated imports,
legacy snapshots, provenance filtering and all routine report types.
