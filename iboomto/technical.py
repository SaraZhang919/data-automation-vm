import csv
import gzip
import io
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin,urlsplit
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from .core import SITE,SF_FOLDER,LANGS,digest,issue,language,stamp
from .storage import request,ApiFailure
from .pages import priority_urls

class PublicSite:
    def __init__(self):
        self.s=requests.Session()
        self.s.headers['User-Agent']='iBoomtoMonitor/1.0 (+https://www.iboomto.com/)'

    def get(self,url):
        # Restrict redirects too: a discovered link cannot send the monitor to arbitrary hosts.
        for _ in range(8):
            p=urlsplit(url)
            if p.scheme!='https' or p.hostname!='www.iboomto.com' or p.port not in (None,443):
                raise ApiFailure('Out-of-scope URL')
            r=self.s.get(url,timeout=25,allow_redirects=False)
            if r.status_code in (301,302,303,307,308) and r.headers.get('Location'):
                url=urljoin(url,r.headers['Location']); continue
            return r
        raise ApiFailure('Redirect loop')

def sitemap_collect(store,web):
    pending=[SITE+'/sitemap-index.xml']; seen=set(); urls=[]; sources=[]
    while pending:
        url=pending.pop(0)
        if url in seen:continue
        seen.add(url)
        try:
            r=web.get(url)
            if r.status_code!=200:raise ApiFailure(f'HTTP {r.status_code}')
            raw=gzip.decompress(r.content) if r.content[:2]==b'\x1f\x8b' else r.content
            root=ET.fromstring(raw)
            kind=root.tag.split('}')[-1]
            if kind not in ('sitemapindex','urlset'):raise ApiFailure('Not sitemap XML')
            count=0
            for node in root:
                vals={n.tag.split('}')[-1]:(n.text or '').strip() for n in node}
                loc=vals.get('loc')
                if not loc:continue
                if kind=='sitemapindex':pending.append(loc)
                else:
                    urls.append({'id':digest([url,loc]),'url':loc,'language':language(loc) or 'unknown','sitemap':url,'lastmod':vals.get('lastmod',''),'observed_at':stamp()});count+=1
            sources.append({'id':url,'status':'success','urls':count,'checked_at':stamp()})
        except Exception as exc:
            sources.append({'id':url,'status':'failed','detail':type(exc).__name__,'checked_at':stamp()})
    complete=all(s['status']=='success' for s in sources)
    old={r['id']:r for r in store.read('Sitemap URLs')}
    for r in urls:r['first_seen']=old.get(r['id'],{}).get('first_seen',r['observed_at'])
    if complete:store.set('Sitemap URLs',urls)
    else:store.upsert('Sitemap URLs',urls)
    previous_sources={r['id']:r for r in store.read('Sitemap Sources')}
    for src in sources:src['last_success_at']=src['checked_at'] if src['status']=='success' else previous_sources.get(src['id'],{}).get('last_success_at','')
    if complete:store.set('Sitemap Sources',sources)
    else:store.upsert('Sitemap Sources',sources)
    changes=[];current={r['id']:r for r in urls}
    for key,r in current.items():
        kind='added' if key not in old else 'lastmod_changed' if r.get('lastmod')!=old[key].get('lastmod') else ''
        if kind:changes.append({'id':digest([stamp(),key,kind]),'change':kind,'url':r['url'],'sitemap':r['sitemap'],'lastmod':r.get('lastmod',''),'previous_lastmod':old.get(key,{}).get('lastmod',''),'observed_at':stamp()})
    if complete:
        for key,r in old.items():
            if key not in current:changes.append({'id':digest([stamp(),key,'removed']),'change':'removed','url':r['url'],'sitemap':r.get('sitemap',''),'observed_at':stamp()})
    store.upsert('Sitemap History',changes)
    return urls,complete

def check_pages(store,web,urls,now):
    priority=priority_urls(store)
    planned={r['url'] for r in store.read('Page Register Checks') if 'not_yet_launched' in r.get('status','')}
    priority|={SITE+'/' if lg=='en' else SITE+'/'+lg for lg in LANGS}
    candidates={r['url'] for r in urls if language(r['url']) is not None}|priority
    candidates|={r['url'] for r in store.read('SF Pages') if str(r.get('status','')).startswith(('4','5')) and language(r['url']) is not None}
    old={r['url']:r for r in store.read('Technical Checks')}
    candidates=sorted(candidates,key=lambda u:(u not in priority,u in old,old.get(u,{}).get('checked_at',''),u))[:500]
    robots=None; robots_status='unavailable'
    try:
        rr=web.get(SITE+'/robots.txt')
        if rr.status_code==200:
            robots=RobotFileParser();robots.parse(rr.text.splitlines());robots_status='available'
        elif rr.status_code==404:robots_status='absent'
    except Exception:pass
    records=[];issues=[];checked=set()
    for url in candidates:
        rec={'id':url,'url':url,'language':language(url),'checked_at':stamp(),'priority':url in priority,'robots_status':robots_status}
        try:
            r=web.get(url)
            if r.status_code>=400:
                time.sleep(.3);r=web.get(url)  # Confirm failures with a fresh request.
            soup=BeautifulSoup(r.content,'html.parser') if 'html' in r.headers.get('Content-Type','') else None
            canonical=soup.find('link',rel='canonical') if soup else None
            tags=soup.find_all('meta',attrs={'name':re_compile_robots()}) if soup else []
            directives=','.join(x.get('content','') for x in tags)+','+r.headers.get('X-Robots-Tag','')
            hreflang={x.get('hreflang'):urljoin(r.url,x.get('href','')) for x in soup.find_all('link',hreflang=True)} if soup else {}
            rec.update({'status':r.status_code,'final_url':r.url,'response_seconds':r.elapsed.total_seconds(),'canonical':urljoin(r.url,canonical.get('href','')) if canonical else '',
                        'robots':directives,'googlebot_allowed':robots.can_fetch('Googlebot',url) if robots else '', 'hreflang':hreflang,'check_status':'success'})
            if robots_status!='unavailable':checked.add(url)
            if r.status_code in (403,429):
                issues.append(issue('monitor_access_blocked',url,'yellow',f'Monitor received HTTP {r.status_code}; verify user and verified crawler access separately',rec['checked_at']))
            elif r.status_code>=400:issues.append(issue('http_error',url,'red' if url in priority else 'yellow',f'Confirmed HTTP {r.status_code}',rec['checked_at']))
            if 'noindex' in directives.lower():issues.append(issue('noindex',url,'red' if url in priority else 'yellow',directives,rec['checked_at']))
            if robots and not rec['googlebot_allowed']:issues.append(issue('robots_blocked',url,'red' if url in priority else 'yellow','Googlebot blocked by robots.txt',rec['checked_at']))
            if '//' in urlsplit(url).path:issues.append(issue('double_slash',url,'yellow','Raw sitemap path contains //',rec['checked_at']))
            if rec['canonical'] and rec['canonical']!=url:issues.append(issue('canonical_mismatch',url,'yellow',rec['canonical'],rec['checked_at']))
            if r.status_code==200 and soup and not canonical:issues.append(issue('canonical_missing',url,'yellow','No HTML canonical element',rec['checked_at']))
        except Exception as exc:
            rec.update({'check_status':'failed','detail':type(exc).__name__})
            issues.append(issue('check_failed',url,'yellow','Could not obtain a reliable HTTP result',rec['checked_at']))
        records.append(rec)
        time.sleep(.1)
    store.upsert('Technical Checks',records)
    for f in issues:
        if f['url'] in planned and f['kind'] in ('http_error','noindex','robots_blocked'):
            f['severity']='observe';f['evidence']={'detail':f['evidence'],'context':'Page register explicitly marks this URL not yet launched; verify launch intent before escalating.'}
    store.set('Technical Findings',issues)
    store.upsert('Technical History',[{**r,'id':digest([r['url'],r['checked_at']])} for r in records])
    store.upsert('Check Coverage',[{'id':now.date().isoformat(),'available_urls':len({r['url'] for r in urls}|priority),'attempted':len(records),'successful':len(checked),'checked_at':stamp()}])
    return issues,checked

def re_compile_robots():
    import re
    return re.compile(r'^(robots|googlebot)$',re.I)

def drive_list(session,parent):
    rows=[];token=None
    while True:
        params={'q':f"'{parent}' in parents and trashed=false",'fields':'nextPageToken,files(id,name,mimeType,modifiedTime,size,md5Checksum)','pageSize':1000}
        if token:params['pageToken']=token
        d=request(session,'GET','https://www.googleapis.com/drive/v3/files',params=params).json()
        rows+=d.get('files',[]);token=d.get('nextPageToken')
        if not token:return rows

def parse_csv(raw,required):
    text=raw.decode('utf-8-sig')
    reader=csv.DictReader(io.StringIO(text))
    if not set(required)<=set(reader.fieldnames or []):raise ApiFailure('CSV headers do not match expected export')
    rows=list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):raise ApiFailure('Malformed CSV')
    return rows

def sf_import(session,store,now):
    folders=[f for f in drive_list(session,SF_FOLDER) if f['mimeType']=='application/vnd.google-apps.folder']
    done={r['id'] for r in store.read('Import Batches') if r.get('status')=='success' and r.get('schema_version')=='compact-v2'}
    latest_time=max((r.get('batch_date','') for r in store.read('Import Batches') if r.get('status')=='success'),default='')
    issues=[]; imported=0
    for folder in sorted(folders,key=lambda f:f['name']):
        if len(folder['name'])!=8 or not folder['name'].isdigit():continue
        files={f['name']:f for f in drive_list(session,folder['id'])}
        names=['internal_all.csv','inlinks.csv','hreflang_all.csv']
        bid=digest([folder['id'],[(n,files.get(n,{}).get('md5Checksum'),files.get(n,{}).get('modifiedTime')) for n in names]])
        if bid in done:continue
        rec={'id':bid,'folder':folder['id'],'source_link':'https://drive.google.com/drive/folders/'+folder['id'],'batch_date':folder['name'],'checked_at':stamp(),'schema_version':'compact-v2'}
        if any(n not in files for n in names):
            store.upsert('Import Batches',[{**rec,'status':'incomplete','detail':'Requires internal_all.csv, inlinks.csv, hreflang_all.csv'}]);continue
        if any((now-datetime.fromisoformat(files[n]['modifiedTime'].replace('Z','+00:00'))).total_seconds()<60 for n in names):continue
        try:
            raw={n:request(session,'GET',f"https://www.googleapis.com/drive/v3/files/{files[n]['id']}",params={'alt':'media'}).content for n in names}
            pages=parse_csv(raw[names[0]],['Address','Status Code','Content Type'])
            links=parse_csv(raw[names[1]],['From','To'])
            hrefs=parse_csv(raw[names[2]],['Address'])
            after={f['name']:f for f in drive_list(session,folder['id'])}
            if any(after.get(n,{}).get('md5Checksum')!=files[n].get('md5Checksum') for n in names):raise ApiFailure('Batch changed during download')
            observed=min((r.get('Crawl Timestamp','') for r in pages if r.get('Crawl Timestamp')),default=folder['name'])
            html=[r for r in pages if 'html' in r['Content Type']]
            page_set={r['Address'] for r in html}
            packed=[]
            for p in html:
                url=p['Address']
                p={k:v for k,v in p.items() if k not in ('Cookies',)}
                ins=sorted({x['From'] for x in links if x['To']==url and x['From'] in page_set})
                packed.append({'id':url,'batch':bid,'batch_date':folder['name'],'url':url,'language':language(url),'crawl_timestamp':p.get('Crawl Timestamp',''),'crawl_timezone':'unspecified',
                    'status':p['Status Code'],'indexability':p.get('Indexability',''),'indexability_status':p.get('Indexability Status',''),
                    'canonical':p.get('Canonical Link Element 1',''),'title':p.get('Title 1',''),'internal_inlinks':len(ins),'inlink_examples':ins[:5],
                    'source_link':rec['source_link']})
                if str(p['Status Code']).startswith(('4','5')):
                    ins=[x['From'] for x in links if x['To']==url]
                    issues.append(issue('sf_http_error',url,'yellow',{'status':p['Status Code'],'inlinks':ins,'batch':bid},observed,'SF Pages'))
            if folder['name']>=latest_time:
                store.set('SF Pages',packed,headers=list(packed[0]) if packed else ['id','url','batch','status','internal_inlinks','source_link'])
                # Raw hreflang remains in Drive; keep only explicit issue flags exported by SF.
                findings=[]
                for r in hrefs:
                    flagged={k:v for k,v in r.items() if v and any(x in k.lower() for x in ('missing','non-200','incorrect','multiple','outside','invalid','unlinked')) and str(v).lower() not in ('0','false','no')}
                    if flagged:findings.append({'id':digest([bid,r['Address']]),'url':r['Address'],'batch':bid,'evidence':flagged,'source_link':rec['source_link']})
                store.set('SF Hreflang Issues',findings,headers=['id','url','batch','evidence','source_link'])
                latest_time=folder['name']
            store.upsert('Import Batches',[{**rec,'status':'success','page_rows':len(pages),'html_rows':len(html),'link_rows':len(links),'hreflang_rows':len(hrefs),'crawl_timestamp':observed,'raw_hashes':{n:digest(raw[n].hex()) for n in names}}])
            imported+=1
        except Exception as exc:
            store.upsert('Import Batches',[{**rec,'status':'failed','detail':type(exc).__name__}])
    from .core import LAUNCH
    age=(now.date()-datetime.strptime(latest_time,'%Y%m%d').date()).days if latest_time else None
    allowed_age=4 if (now.date()-LAUNCH).days<30 else 7
    state='waiting_for_upload' if not latest_time else 'stale' if age>allowed_age else 'success'
    return issues,{'imported':imported,'latest_batch':latest_time,'age_days':age,'status':state}

def clarity_collect(store,token,now,api=None):
    from .clarity import collect
    return collect(store,token,now,api)
