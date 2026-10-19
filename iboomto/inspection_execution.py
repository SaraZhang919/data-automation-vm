"""Shared inspection observations and bounded, stoppable manual execution."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from .core import stamp


def provenance(run_id, trigger_type=None):
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    server = os.environ.get('GITHUB_SERVER_URL', 'https://github.com')
    trigger = trigger_type or ('scheduled' if os.environ.get('GITHUB_EVENT_NAME') == 'schedule' else 'manual')
    return {'trigger_type': trigger, 'run_id': str(run_id),
            'run_url': f'{server}/{repository}/actions/runs/{run_id}' if repository else ''}


def inspect_one(api, url, origin):
    base = {'id': url, 'url': url, **origin}
    try:
        result = api.inspection(url)
        state = result.get('indexStatusResult', {})
        return {**base, 'checked_at': stamp(), 'api_status': 'success',
                'verdict': state.get('verdict', ''), 'coverage_state': state.get('coverageState', ''),
                'last_crawl_time': state.get('lastCrawlTime', ''),
                'google_canonical': state.get('googleCanonical', ''),
                'user_canonical': state.get('userCanonical', ''),
                'page_fetch_state': state.get('pageFetchState', ''),
                'inspection_link': result.get('inspectionResultLink', ''), 'result': result}
    except Exception as exc:
        return {**base, 'checked_at': stamp(), 'api_status': 'failed',
                'error_type': type(exc).__name__, 'http_status': getattr(exc, 'status_code', None)}


def inspect_batch(urls, api_factory, origin, on_result, max_workers=4):
    """Only keep four requests in flight; stop launching on permission/quota errors."""
    worker = threading.local()
    stop = threading.Event()
    pending_urls = iter(urls)
    attempted = set()
    stop_reason = ''

    def request(url):
        if stop.is_set():
            return None
        try:
            if not hasattr(worker, 'api'):
                worker.api = api_factory()
            row = inspect_one(worker.api, url, origin)
        except Exception as exc:
            row = {'id': url, 'url': url, **origin, 'checked_at': stamp(),
                   'api_status': 'failed', 'error_type': type(exc).__name__, 'http_status': None}
            stop.set()
        if row.get('http_status') in (401, 403, 429):
            stop.set()
        return row

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}

        def fill():
            while not stop.is_set() and len(futures) < max_workers:
                url = next(pending_urls, None)
                if url is None:
                    break
                futures[pool.submit(request, url)] = url

        fill()
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                url = futures.pop(future)
                row = future.result()
                if row is not None:
                    attempted.add(url)
                    if row.get('http_status') in (401, 403, 429):
                        stop_reason = 'permission_or_quota_exhaustion'
                    elif stop.is_set() and not stop_reason:
                        stop_reason = 'request_initialization_failed'
                    try:
                        on_result(row)
                    except Exception:
                        stop.set()
                        raise
            fill()
    return [u for u in urls if u not in attempted], stop_reason
