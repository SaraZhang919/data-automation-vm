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
    store.upsert('Sitemap Sources',sources)
    store.upsert('Sitemap History',[{'id':digest([stamp(),r['id']]),**{k:v for k,v in r.items() if k!='id'}} for r in urls])
    return urls,complete

def check_pages(store,web,urls,now):
    priority={r['url'] for r in store.read('Priority Pages') if r.get('enabled',True) not in (False,'false','FALSE') and r.get('url')}
    priority|={SITE+'/' if lg=='en' else SITE+'/'+lg for lg in LANGS}
    candidates={r['url'] for r in urls if language(r['url']) is not None}|priority
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
            checked.add(url)
            if r.status_code>=400:issues.append(issue('http_error',url,'red' if url in priority else 'yellow',f'Confirmed HTTP {r.status_code}',rec['checked_at']))
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
    done={r['id'] for r in store.read('Import Batches') if r.get('status')=='success'}
    latest_time=max((r.get('batch_date','') for r in store.read('Import Batches') if r.get('status')=='success'),default='')
    issues=[]; imported=0
    for folder in sorted(folders,key=lambda f:f['name']):
        if len(folder['name'])!=8 or not folder['name'].isdigit():continue
        files={f['name']:f for f in drive_list(session,folder['id'])}
        names=['internal_all.csv','inlinks.csv','hreflang_all.csv']
        bid=digest([folder['id'],[(n,files.get(n,{}).get('md5Checksum'),files.get(n,{}).get('modifiedTime')) for n in names]])
        if bid in done:continue
        rec={'id':bid,'folder':folder['id'],'batch_date':folder['name'],'checked_at':stamp()}
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
                packed.append({'id':digest([bid,url]),'batch':bid,'batch_date':folder['name'],'url':url,'language':language(url),'crawl_timestamp':p.get('Crawl Timestamp',''),'crawl_timezone':'unspecified','status':p['Status Code'],'data':p})
                if str(p['Status Code']).startswith(('4','5')):
                    ins=[x['From'] for x in links if x['To']==url]
                    issues.append(issue('sf_http_error',url,'yellow',{'status':p['Status Code'],'inlinks':ins,'batch':bid},observed,'SF Pages'))
            store.upsert('SF Pages',packed)
            if folder['name']>=latest_time:
                store.set('SF Links Latest',[{'id':digest([bid,i]),'batch':bid,'batch_date':folder['name'],**r} for i,r in enumerate(links)])
                store.set('SF Hreflang Latest',[{'id':digest([bid,r['Address']]),'batch':bid,'batch_date':folder['name'],**r} for r in hrefs])
                latest_time=folder['name']
            store.upsert('Import Batches',[{**rec,'status':'success','page_rows':len(pages),'html_rows':len(html),'link_rows':len(links),'hreflang_rows':len(hrefs),'crawl_timestamp':observed,'raw_hashes':{n:digest(raw[n].hex()) for n in names}}])
            imported+=1
        except Exception as exc:
            store.upsert('Import Batches',[{**rec,'status':'failed','detail':type(exc).__name__}])
    return issues,{'imported':imported,'latest_batch':latest_time,'status':'success' if latest_time else 'waiting_for_upload'}

def clarity_collect(store,token,now):
    if not token:return {'status':'not_configured','detail':'CLARITY_API_TOKEN missing'}
    # Skip repeats on the same JST day. Each view consumes one of the project-wide 10 requests.
    from zoneinfo import ZoneInfo
    day=now.astimezone(ZoneInfo('Asia/Tokyo')).date().isoformat()
    done={r['id'] for r in store.read('Clarity Requests') if r.get('status')=='success'}
    session=requests.Session(); session.headers['Authorization']='Bearer '+token
    for view in ('overall','URL','Device'):
        rid=digest([day,view])
        if rid in done:continue
        ledger=store.read('Clarity Requests')
        attempts=sum(int(r.get('attempts',0)) for r in ledger if r.get('day')==day)
        if attempts>=8:return {'status':'quota_guard','detail':'Local request allowance exhausted; leave capacity for other clients'}
        params={'numOfDays':1}
        if view!='overall':params['dimension1']=view
        # No automatic HTTP retry for this low daily-quota API.
        r=session.get('https://www.clarity.ms/export-data/api/v1/project-live-insights',params=params,timeout=60)
        previous=next((x for x in ledger if x.get('id')==rid),{})
        store.upsert('Clarity Requests',[{'id':rid,'day':day,'view':view,'attempts':int(previous.get('attempts',0))+1,'status':'success' if r.status_code==200 else 'failed','http_status':r.status_code,'at':stamp()}]);store.flush()
        if r.status_code!=200:raise ApiFailure(f'Clarity HTTP {r.status_code}')
        payload=r.json();packed=[]
        for metric in payload:
            infos=metric.get('information',[])
            for i,info in enumerate(infos):
                url=info.get('URL','')
                packed.append({'id':digest([rid,metric.get('metricName'),i]),'day':day,'view':view,'metric':metric.get('metricName'),
                               'window_start':(now-timedelta(hours=24)).isoformat(),'window_end':now.isoformat(),'window_type':'rolling_24h','timezone':'UTC',
                               'language':language(url) if url else '', 'coverage':'possibly_truncated' if len(infos)>=1000 else 'returned_rows','data':info,'collected_at':stamp()})
        store.upsert('Clarity Daily',packed)
    return {'status':'success'}
