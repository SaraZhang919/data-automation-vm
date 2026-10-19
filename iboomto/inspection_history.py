"""Persist observed indexing milestones, never Google's actual indexing time."""
import json
from .core import digest, language


def observed_state(row):
    if row.get('api_status') != 'success':
        return 'unknown'
    result = row.get('result') or {}
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            result = {}
    state = result.get('indexStatusResult', {}) if isinstance(result, dict) else {}
    verdict = row.get('verdict') or state.get('verdict')
    return {'PASS': 'indexed', 'FAIL': 'not_indexed', 'NEUTRAL': 'not_indexed'}.get(verdict, 'unknown')


def merge_observation(previous, current, basis='new_observation'):
    row = {**previous, **current}
    url = row['url']
    row['language'] = language(url) or ''
    for field in ('first_observed_indexed_at', 'last_observed_not_indexed_at',
                  'first_observed_indexed_basis', 'index_state_observed_at'):
        row.setdefault(field, '')
    before = previous.get('last_known_index_state', 'unknown')
    state = observed_state(current)
    when = current.get('checked_at', '')
    row['latest_attempt_index_state'] = state
    row['last_known_index_state'] = before
    if current.get('api_status') == 'success':
        row['last_successful_checked_at'] = when
        row['error_type'] = ''
        row['http_status'] = ''
    # Failed calls preserve previous index evidence and milestones; unknown
    # responses never masquerade as de-indexing or move the known-state clock.
    if state == 'unknown' or not when:
        # Preserve the evidence supporting the last conclusive state, even when
        # a successful API response contains an unspecified/unknown verdict.
        if before in ('indexed', 'not_indexed'):
            for field in ('verdict', 'coverage_state', 'last_crawl_time', 'google_canonical',
                          'user_canonical', 'page_fetch_state', 'inspection_link', 'result'):
                if field in previous:
                    row[field] = previous[field]
        return row, None
    previous_observed_at = previous.get('index_state_observed_at', '')
    row['last_known_index_state'] = state
    row['index_state_observed_at'] = when
    if state == 'indexed' and not row['first_observed_indexed_at']:
        row['first_observed_indexed_at'] = when
        row['first_observed_indexed_basis'] = basis
    if state == 'not_indexed':
        row['last_observed_not_indexed_at'] = when
    if before == state:
        return row, None
    event = {
        'id': digest([url, before, state, when]), 'url': url, 'language': row['language'],
        'event_type': 'baseline' if before == 'unknown' else 'state_change',
        'previous_state': before, 'current_state': state,
        'previous_observed_at': previous_observed_at, 'observed_at': when,
        'observation_basis': basis, 'verdict': current.get('verdict', ''),
        'coverage_state': current.get('coverage_state', ''),
        'meaning': 'Observed state only; not the actual Google indexing timestamp'}
    if basis == 'new_observation':
        event.update({key: current[key] for key in ('trigger_type', 'run_id', 'run_url') if key in current})
    return row, event


def seed_observations(rows):
    """Seed once from surviving snapshots; overwritten history is unrecoverable."""
    seeded = []
    events = []
    for original in rows:
        if original.get('observation_tracking_version') == 'v1':
            seeded.append(original)
            continue
        row, event = merge_observation({}, original, 'retained_snapshot')
        row['observation_tracking_version'] = 'v1'
        seeded.append(row)
        if event:
            events.append(event)
    return seeded, events
