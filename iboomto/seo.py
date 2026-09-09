import json
from .core import digest,issue,language,stamp

def as_dict(value):
    return json.loads(value) if isinstance(value,str) else value

def seo_findings(store):
    issues=[];summary=[]
    checks={r['url']:r for r in store.read('Technical Checks') if r.get('check_status')=='success'}
    for url,r in checks.items():
        alternates=as_dict(r.get('hreflang',{}))
        for lang,target in alternates.items():
            if lang=='x-default':continue
            expected='zh-Hant' if language(target)=='zh-tw' else language(target)
            if expected and lang.lower()!=expected.lower():
                issues.append(issue('hreflang_language',url,'yellow',{'declared':lang,'target':target,'expected':expected},r['checked_at']))
            other=checks.get(target)
            if not other:continue
            if str(other.get('status'))!='200':
                issues.append(issue('hreflang_target_error',url,'yellow',{'target':target,'status':other.get('status')},r['checked_at']))
            # Reciprocity is checked only against successfully retrieved targets in this run.
            if other.get('checked_at','')[:10]!=r['checked_at'][:10]:continue
            reciprocal=as_dict(other.get('hreflang',{}))
            if url not in reciprocal.values():
                issues.append(issue('hreflang_return_missing',url,'yellow',{'target':target},r['checked_at']))
    batches=[r for r in store.read('Import Batches') if r.get('status')=='success']
    if batches:
        latest=max(batches,key=lambda r:(r['batch_date'],r.get('checked_at','')))
        pages={r['url']:r for r in store.read('SF Pages') if r.get('batch')==latest['id']}
        sitemap={r['url']:r for r in store.read('Sitemap URLs')}
        linked={u for u,r in pages.items() if float(r.get('internal_inlinks') or 0)>0}
        for url,r in sitemap.items():
            found=url in pages
            note='crawled' if found else 'not_in_latest_crawl'
            first=str(r.get('first_seen','')).replace('-','')[:8]
            if not found and first>=latest['batch_date']:note='waiting_for_next_crawl'
            summary.append({'id':url,'url':url,'language':language(url),'sf_batch_date':latest['batch_date'],'status':note,'has_internal_inlink':url in linked,'checked_at':stamp()})
            if found and url not in linked and urlsplit_path(url) not in ('','/'):
                issues.append(issue('no_internal_inlink_in_export',url,'yellow','No inlink from crawled HTML pages; orphan candidate, not confirmed orphan',latest.get('crawl_timestamp',latest['batch_date']),'SF Pages'))
        store.set('Sitemap Crawl Comparison',summary)
    return issues

def urlsplit_path(url):
    from urllib.parse import urlsplit
    return urlsplit(url).path
