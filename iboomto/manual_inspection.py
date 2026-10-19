"""Inspect a chosen stored URL inventory, without invoking other collectors."""
import html
import json
import multiprocessing
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo
from .core import DATA_ID, LANGS, digest, language, stamp
from .inspection_execution import inspect_batch, provenance
from .inspection_history import merge_observation, seed_observations

LIMIT = 1000
REMINDER = ('Maximum 1,000 URLs per run. Leave both URLs and URL regex blank to inspect all known URLs '
            'in the selected language, or all languages if Language = all.')
INVENTORY = (('Sitemap URLs', 'url', 'observed_at'),
             ('Page name - manual management', 'Urls', None),
             ('URL Inspection', 'url', 'checked_at'))


def valid_url(value):
    value = str(value or '').strip()
    try:
        p = urlsplit(value)
        if (p.scheme != 'https' or p.netloc.lower() != 'www.iboomto.com' or
                p.query or p.fragment or any(c.isspace() or ord(c) < 32 for c in value) or
                any(c in value for c in ('\\', '\u200b', '\ufeff')) or '//' in p.path or
                language(value) is None):
            raise ValueError()
    except ValueError:
        raise ValueError('Use canonical HTTPS content URLs on www.iboomto.com, without query strings or fragments.') from None
    return urlunsplit(('https', 'www.iboomto.com', p.path or '/', '', ''))


def validate_inputs(raw_urls, pattern, selected_language):
    if selected_language not in ('all', *LANGS):
        raise ValueError('Unknown language.')
    if raw_urls.strip() and pattern.strip():
        raise ValueError('URLs and URL regex are mutually exclusive. Supply only one.')
    if pattern.strip():
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f'Invalid URL regex: {exc.msg}') from None
    explicit = []
    if raw_urls.strip():
        for value in re.split(r'[,\r\n]+', raw_urls):
            if not value.strip():
                continue
            url = valid_url(value)
            if selected_language != 'all' and language(url) != selected_language:
                raise ValueError(f'URL language conflicts with selected language: {url}')
            explicit.append(url)
        if not explicit:
            raise ValueError('Enter at least one URL, or leave URLs completely blank.')
        explicit = sorted(set(explicit))
        enforce_limit(explicit)
    return explicit


def enforce_limit(urls):
    if len(urls) > LIMIT:
        raise ValueError(f'{len(urls):,} URLs selected; maximum is 1,000. Narrow the language or regex. Nothing was inspected.')


def _regex_worker(connection, pattern, urls):
    try:
        regex = re.compile(pattern)
        connection.send([i for i, url in enumerate(urls) if regex.search(url)])
    finally:
        connection.close()


def regex_filter(urls, pattern, timeout=5):
    # A separate process bounds Python re backtracking on both Linux and Windows.
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_regex_worker, args=(sender, pattern, urls))
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout):
            raise ValueError('URL regex evaluation exceeded 5 seconds. Simplify the pattern; nothing was inspected.')
        return [urls[i] for i in receiver.recv()]
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join()


def select_urls(store, explicit, pattern, selected_language):
    if explicit:
        return explicit, []
    urls = set()
    freshness = []
    for tab, field, date_field in INVENTORY:
        rows = store.read(tab)
        dates = []
        accepted = 0
        invalid = 0
        missing_dates = 0
        for row in rows:
            try:
                url = valid_url(row.get(field))
            except ValueError:
                invalid += 1
                continue
            if selected_language != 'all' and language(url) != selected_language:
                continue
            urls.add(url)
            accepted += 1
            observed = row.get(date_field) if date_field else None
            if observed:
                dates.append(str(observed))
            else:
                missing_dates += 1
        freshness.append({'source': tab, 'candidate_rows': accepted, 'invalid_rows_skipped': invalid,
                          'oldest_observation': min(dates, default='unknown'),
                          'latest_observation': max(dates, default='unknown'),
                          'rows_without_timestamp': missing_dates})
    selected = sorted(urls)
    if pattern.strip():
        selected = regex_filter(selected, pattern)
    enforce_limit(selected)
    return selected, freshness


def execute(store, api_factory, urls, origin, report, checkpoint):
    if not urls:
        report.update(status='success', message='No matching URLs')
        return
    # Seed only selected rows: a targeted check must not rewrite unrelated URLs.
    selected = set(urls)
    existing = [r for r in store.read('URL Inspection') if r.get('url') in selected]
    seeded, seed_history = seed_observations(existing)
    previous = {r['url']: r for r in seeded}
    seeded_events = {r['url']: r for r in seed_history}
    waiting_rows, waiting_history = [], []

    def flush():
        if waiting_rows:
            store.upsert('URL Inspection', waiting_rows)
        if waiting_history:
            store.upsert('URL Inspection History', waiting_history)
        if waiting_rows or waiting_history:
            store.flush()
        waiting_rows.clear()
        waiting_history.clear()

    def accept(current):
        row, event = merge_observation(previous.get(current['url'], {}), current)
        row['observation_tracking_version'] = 'v1'
        waiting_rows.append(row)
        if current['url'] in seeded_events:
            waiting_history.append(seeded_events[current['url']])
        if event:
            waiting_history.append(event)
        # The artifact holds this attempt's response, not stale retained evidence.
        report['results'].append({**current, 'latest_attempt_index_state': row['latest_attempt_index_state'],
                                  'last_known_index_state': row['last_known_index_state']})
        report['successful' if current['api_status'] == 'success' else 'failed'] += 1
        attempted = {r['url'] for r in report['results']}
        report['unchecked_urls'] = [u for u in urls if u not in attempted]
        checkpoint()
        if len(waiting_rows) >= 20:
            flush()

    try:
        unchecked, reason = inspect_batch(urls, api_factory, origin, accept)
        report['unchecked_urls'] = unchecked
        report['stop_reason'] = reason
    finally:
        flush()
    report['status'] = 'failed' if report['failed'] or report['unchecked_urls'] else 'success'


def summary(report, sheet_url):
    esc = lambda v: html.escape(str(v), quote=True)
    started = datetime.fromisoformat(report['started_at']).astimezone(ZoneInfo('Asia/Tokyo')).isoformat()
    inventory = []
    for source in report['inventory']:
        source = dict(source)
        for field in ('oldest_observation', 'latest_observation'):
            try:
                moment = datetime.fromisoformat(source[field])
                if moment.tzinfo:
                    source[field] = moment.astimezone(ZoneInfo('Asia/Tokyo')).isoformat()
            except (ValueError, KeyError):
                pass
        inventory.append(source)
    lines = ['## Manual URL Inspection — iBoomto', '', REMINDER, '',
             'Google indexed-state API only; this is not a live test or an indexing request.', '',
             f"Started (JST): {started}", '',
             f"Status: **{report['status']}**. {esc(report.get('message', ''))}", '',
             f"Selected: **{report['selected']}** · Successful API responses: **{report['successful']}** · "
             f"Failed: **{report['failed']}** · Unchecked: **{len(report['unchecked_urls'])}**", '',
             f"[Open monitoring workbook]({sheet_url})", '',
             '<details><summary>Selection and inventory freshness</summary><pre>' +
             esc(json.dumps({'selection': report['selection'], 'inventory': inventory}, ensure_ascii=False, indent=2)) +
             '</pre></details>', '',
             '<details><summary>Inspection results</summary><table><tr><th>URL</th><th>API status</th><th>Observed state / error</th></tr>']
    for row in report['results']:
        lines.append('<tr><td>' + esc(row['url']) + '</td><td>' + esc(row['api_status']) +
                     '</td><td>' + esc(row.get('coverage_state') or row.get('error_type') or 'unknown') + '</td></tr>')
    lines.append('</table></details>')
    if report['unchecked_urls']:
        lines.extend(['', '<details><summary>Unchecked URLs</summary><pre>',
                      esc('\n'.join(report['unchecked_urls'])), '</pre></details>'])
    if report.get('stop_reason'):
        lines.extend(['', 'Stopped: ' + esc(report['stop_reason'])])
    return '\n'.join(lines) + '\n'


def main():
    from .analytics import Analytics
    from .api_usage import METER
    from .storage import Sheets, google_session
    raw_urls = os.environ.get('INPUT_URLS', '')
    pattern = os.environ.get('INPUT_URL_REGEX', '')
    selected_language = os.environ.get('INPUT_LANGUAGE') or 'all'
    run_id = os.environ.get('GITHUB_RUN_ID') or digest(stamp())
    origin = provenance(run_id, 'manual')
    sheet_id = os.environ.get('IBOOMTO_SHEET_ID') or DATA_ID
    report = {**origin, 'started_at': stamp(), 'status': 'running', 'selected': 0,
              'successful': 0, 'failed': 0, 'unchecked_urls': [], 'results': [], 'inventory': [],
              'selection': {'language': selected_language, 'urls': raw_urls, 'url_regex': pattern}}
    output = Path('runtime/manual-url-inspection.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    store = None
    METER.reset(run_id)

    def checkpoint():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    try:
        # Invalid input/regex is rejected before authentication or any API call.
        explicit = validate_inputs(raw_urls, pattern, selected_language)
        store = Sheets(google_session(), sheet_id, write=True)
        urls, report['inventory'] = select_urls(store, explicit, pattern, selected_language)
        report.update(selected=len(urls), unchecked_urls=list(urls))
        checkpoint()
        execute(store, lambda: Analytics(google_session()), urls, origin, report, checkpoint)
    except Exception as exc:
        report['status'] = 'failed'
        report['message'] = str(exc) if isinstance(exc, ValueError) else f'{type(exc).__name__}: inspection could not complete.'
    finally:
        report['finished_at'] = stamp()
        if store is not None:
            try:
                store.upsert('Run Status', [{**origin, 'id': digest([run_id, 'Manual URL Inspection']),
                             'source': 'Manual URL Inspection', 'status': report['status'],
                             'started_at': report['started_at'], 'finished_at': report['finished_at'],
                             'detail': {k: report[k] for k in ('selected', 'successful', 'failed')} |
                                       {'unchecked': len(report['unchecked_urls']), 'message': report.get('message', ''),
                                        'stop_reason': report.get('stop_reason', '')}}])
                store.upsert('API Usage', METER.rows())
                store.flush()
            except Exception as exc:
                report.update(status='failed', persistence_error=type(exc).__name__)
                report['message'] = 'Sheet persistence failed; inspect the per-run artifact for completed responses.'
        report['api_usage'] = METER.rows()
        checkpoint()
        text = summary(report, 'https://docs.google.com/spreadsheets/d/' + sheet_id + '/edit')
        Path('runtime/manual-url-inspection-summary.md').write_text(text, encoding='utf-8')
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
                handle.write(text)
        print(json.dumps({k: report[k] for k in ('status', 'selected', 'successful', 'failed')}))
    return 0 if report['status'] == 'success' else 1


if __name__ == '__main__':
    sys.exit(main())
