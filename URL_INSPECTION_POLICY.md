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

This change adds no historical snapshot table and does not change failed-result
storage behavior. No extra GA, Search Analytics or LLM requests are introduced.
Selection code: `iboomto/inspection.py`. The optional environment variable
`IBOOMTO_INSPECTION_PER_LANGUAGE_LIMIT` defaults to 30, capped at 100; other limits
split approximately into thirds. Daily limits assume one daily run, not repeated
manual runs.
