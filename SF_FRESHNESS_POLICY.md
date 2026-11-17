# Screaming Frog import and freshness for routine reports

Screaming Frog crawls are manual. Upload `internal_all.csv`, `inlinks.csv`
and `hreflang_all.csv` to one `YYYYMMDD` subfolder named for the crawl's
start date in Japan Standard Time (JST).

- Each run can import one new batch. It looks for the newest complete
  export first and will not replace a newer crawl with an older one.
  A delayed run can pick up a previous day's upload. Incomplete,
  changing, future-dated and duplicate batches cannot replace the snapshot.
- The earliest `Crawl Timestamp` in `internal_all.csv` must match the
  folder's JST date. All supplied timestamps must parse and cannot be
  in the future. Timestamps without a timezone are treated as JST.
  Upload time is used for file stability, never as a crawl timestamp.
- Only the latest verified snapshot, if its crawl started today or yesterday
  JST, can support current SF findings, SEO comparisons, and extra HTTP
  check candidates. Independently selected pages still receive live checks.
  The latest validated batch can be recovered after that window, but its
  SF findings are historical, with the actual crawl date retained.
- Inactive SF findings are kept as historical evidence. Missing or aging SF
  data does not mark an issue fixed. A fresh snapshot is one crawl, even
  when it is cited in a weekly or monthly report.

Successful new imports use `latest-verified-v2`. Verified imports under
`same-jst-day-v1` are still recognized. Unverified legacy imports do not
qualify as current evidence. Existing Drive exports and historical reports
are not rewritten.
