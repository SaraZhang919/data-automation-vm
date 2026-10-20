# GA4 Referral

`GA4 Referral` stores the top 30 **session sources by sessions** for each language
property and daily, weekly or monthly period. The dimension is `sessionSource`;
the filter is `sessionDefaultChannelGroup = Referral` plus the existing production
hostname filter `hostName EXACT www.iboomto.com`.

Each day has its own top 30. Weeks follow Sunday–Saturday; months are calendar
months. Each week/month is queried directly through GA4; users and rates are not
summed from daily data. Source rankings can change between periods. There can be
fewer than 30 sources. This is a selected-source report, not a channel total.

Columns include period, start/end, language, rank, session_source, channel,
sessions, activeUsers, totalUsers, newUsers, engagedSessions, engagementRate,
averageSessionDuration, eventCount, keyEvents and key_events_per_user. eventCount
includes all events; keyEvents includes events marked key in GA4. Neither is a
confirmed software download count. Metrics keep GA4's native attribution.

Language follows the existing nine property mappings. Statistical dates follow
each property's timezone. collected_at is UTC. quality flags preserve provisional,
thresholded/limited and partial-launch periods. Empty API responses retain an
explicit no_data_returned coverage row with blank metrics, not invented sources.

The existing monitor refreshes daily data over its recent seven completed dates
and collects weekly/monthly data with the existing period jobs. Request pacing,
credentials, operational logs, Sheets writer concurrency and retention policies
are shared with the other GA4 tables. Refreshing a partition replaces its prior
top 30; failed requests leave that partition's previous evidence intact.

The **GA4 Referral backfill — iBoomto** workflow fills history from the September
7, 2026 launch through the previous completed property date, all completed weeks
and months, including launch partials. It only queries referral data and writes
the referral table, data revisions, operational status and API usage. It is
idempotent and publishes a JSON audit artifact and Sheet link in the run summary.
It does not require an additional GA4 key event or tracking change.
