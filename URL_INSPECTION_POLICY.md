# URL Inspection rotation

Each daily run selects up to 30 URLs per language (270 across nine languages).
The existing schedule and per-URL replacement writes are unchanged.

Each language reserves 10 slots for never-queried URLs, 10 for due follow-ups,
and 10 for ordinary oldest-first rotation. Manual pages come first in discovery.
Follow-ups include failed API calls and evidence of non-indexing without a known
noindex, redirect, robots exclusion, duplicate/alternate canonical or 404 state.
These exclusions still receive ordinary rotation; they are not declared harmless.
Status is inferred from the stored Google index response, not a live page test.

Non-indexed follow-ups wait at least 72 hours since the last query. Failed API
calls may retry on the next Japan-calendar day. Cooldowns also apply when filling
spare slots. Unused slots are filled from discovery, due follow-ups, then regular
rotation, without duplication or transferring capacity between languages.
Regular rotation ensures indexed URLs are still checked. There may be fewer than
30 eligible URLs in a language; no repeated requests are made to fill its quota.

No extra GA, Search Analytics or LLM requests are introduced.
Selection code: `iboomto/inspection.py`. The optional environment variable
`IBOOMTO_INSPECTION_PER_LANGUAGE_LIMIT` defaults to 30, capped at 100; other limits
split approximately into thirds. Daily limits assume one daily run, not repeated
manual runs.

## Observed indexing history

`URL Inspection` remains one latest row per URL. New columns append to the right:

- `first_observed_indexed_at`: earliest retained observation of indexed status;
  never overwritten by subsequent checks or loss/recovery of indexing.
- `last_observed_not_indexed_at`: latest successful non-indexed observation.
- `first_observed_indexed_basis`: `retained_snapshot` for an existing snapshot
  used at rollout, or `new_observation` for observations after rollout.
- `last_known_index_state` and `index_state_observed_at`: last conclusive state
  and its observation time. `latest_attempt_index_state` can be `unknown`.
- `last_successful_checked_at`: time of the most recent successful API call.

`URL Inspection History` records the first known baseline and subsequent
indexed/not_indexed transitions. Repeated unchanged observations add no rows.
Events include URL, language, previous/current state, both observation timestamps
and evidence. The interval between observations is not an exact indexing time.
Only successful indexStatusResult PASS maps to indexed; FAIL/NEUTRAL map to
not_indexed. Missing, reserved or unknown verdicts and API errors are unknown.
This uses the index verdict, not robots permission or last crawl time.

The next daily technical run seeds existing successful snapshots once, with
`retained_snapshot` labels. Previously overwritten observations cannot be
recovered. All stored timestamps are UTC ISO strings. Failed requests retain
previous index evidence and milestones and do not create de-indexing events.
No live Sheet rewrite is required before the scheduled run; ordinary storage
preserves existing column positions and appends new columns.
