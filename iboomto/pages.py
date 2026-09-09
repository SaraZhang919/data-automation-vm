"""The user-owned page register is the single page metadata/priority source."""
from urllib.parse import urlsplit, urlunsplit
from .core import SITE, LANGS, language, digest, stamp

REGISTER = 'Page name - manual management'
TOP_PAGES = 30
TOP_QUERIES = 100

def pure_url(url):
    p = urlsplit(str(url).strip())
    if not p.netloc and p.path.startswith('/'):
        return SITE + (p.path or '/')
    return urlunsplit((p.scheme, p.netloc, p.path or '/', '', ''))

def registry(store):
    pages = {}; checks = []
    for i, row in enumerate(store.read(REGISTER), 2):
        raw = str(row.get('Urls', '')).strip()
        url = pure_url(raw) if raw else ''
        lg = language(url) if url else None
        label = str(row.get('Lan', '')).lower().strip()
        label = {'jp':'ja', 'tw':'zh-tw', 'br':'pt'}.get(label, label)
        problems = []
        if not raw: problems.append('missing_url')
        elif not url.startswith(SITE + '/') or lg is None: problems.append('invalid_url')
        else:
            if '//' in urlsplit(url).path: problems.append('double_slash')
            if label and label != lg: problems.append('language_conflict')
            if url in pages: problems.append('duplicate_url')
            pages.setdefault(url, {'page_type':row.get('Page Type',''), 'page_name':row.get('Page Name',''),
                                   'registry_row':i, 'declared_language':label})
        if any('未上线' in str(v) for v in row.values()): problems.append('not_yet_launched')
        checks.append({'id':str(i), 'registry_row':i, 'url':raw, 'language':lg or '',
                       'status':','.join(problems) or 'valid', 'checked_at':stamp()})
    store.set('Page Register Checks', checks)
    return pages

def priority_urls(store):
    return set(registry(store))

def page_fields(url, pages):
    pure = pure_url(url)
    lg = language(pure) or 'unknown'
    segments = urlsplit(pure).path.strip('/').split('/')
    if segments and segments[0] in LANGS[1:]: segments = segments[1:]
    return {'language_path':lg, 'subfolder':segments[0] if segments and segments[0] else '/',
            'page_type':pages.get(pure,{}).get('page_type',''),
            'page_name':pages.get(pure,{}).get('page_name',''), 'page_url':pure}

def selected_pages(top, pages, lg, previous=()):
    selected = {pure_url(u):'top30' for u in top if language(u) == lg}
    for u in previous:
        if language(u) == lg: selected.setdefault(pure_url(u),'previous_top30')
    for u in pages:
        if language(u) == lg:
            selected[u] = 'manual+' + selected[u] if u in selected else 'manual'
    return selected
