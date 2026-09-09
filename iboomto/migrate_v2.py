"""Explicit, backed-up v2 migration. Not part of the scheduled collection path."""
import argparse,json,gzip
from pathlib import Path
from .core import DATA_ID,load_local_env,digest,stamp
from .storage import Sheets,google_session,request
from .collectors import scope,SCOPE_VERSION,HOST
from .guide import update_guide
from .pages import registry
from .backup import REPORT_ID

def rename(store,old,new):
    if old not in store.tabs or new in store.tabs:return
    sid=store.tabs[old]['sheetId']
    request(store.s,'POST',store.base+':batchUpdate',json={'requests':[{'updateSheetProperties':{'properties':{'sheetId':sid,'title':new},'fields':'title'}}]})
    prop=store.tabs.pop(old);prop['title']=new;store.tabs[new]=prop

def remove(store,names):
    req=[{'deleteSheet':{'sheetId':store.tabs[n]['sheetId']}} for n in names if n in store.tabs]
    if req:request(store.s,'POST',store.base+':batchUpdate',json={'requests':req})
    for n in names:
        store.tabs.pop(n,None);store.cache.pop(n,None);store.headers.pop(n,None);store.dirty.discard(n)

def main():
    p=argparse.ArgumentParser();p.add_argument('--env-file');p.add_argument('--backup',required=True);p.add_argument('--cleanup',action='store_true');a=p.parse_args()
    if a.env_file:load_local_env(a.env_file)
    for sid in (DATA_ID,REPORT_ID):
        snapshot=json.loads(gzip.decompress((Path(a.backup)/(sid+'.json.gz')).read_bytes()))
        if snapshot['id']!=sid:raise ValueError('Backup ID mismatch')
    s=google_session();store=Sheets(s,DATA_ID,True);report=Sheets(s,REPORT_ID,True)
    if a.cleanup:
        # Only retire SF raw tables once the compact import has actually succeeded.
        latest=max(store.read('Import Batches'),key=lambda r:(r.get('batch_date',''),r.get('checked_at','')),default={})
        safe=['Priority Pages','Page Map','Event Candidates','Metric Comparisons','Period Comparisons']
        if latest.get('status')=='success' and latest.get('schema_version')=='compact-v2':safe+=['SF Links Latest','SF Hreflang Latest']
        remove(store,safe);update_guide(store,report);store.flush();print(json.dumps({'removed':safe}));return
    rename(store,'GA4 Daily','GA4 Site');rename(store,'GSC Daily','GSC Site');rename(report,'Daily History','Report History')
    # Consolidate any existing cycle tabs without recomputing users or losing source records.
    retired=[]
    for name in list(store.tabs):
        parts=name.split(' ')
        if len(parts)>=3 and parts[0] in ('GA4','GSC') and parts[1] in ('Weekly','Monthly','Rolling28'):
            suffix=' '.join(parts[2:]);target=parts[0]+' '+('Site' if suffix=='Daily' else suffix)
            store.upsert(target,store.read(name));retired.append(name)
    for name in ('GA4 Site','GA4 Channels','GA4 Landing Pages','GA4 Events'):
        rows=[]
        for row in store.read(name):
            r=dict(row);sc=r.get('scope',{});sc=json.loads(sc) if isinstance(sc,str) else sc
            r.update(scope=scope(sc.get('exact',''),sc.get('prefix',''),True),hostname_filter='hostName EXACT '+HOST,scope_version=SCOPE_VERSION)
            dim=r.get('dimensions',{});dim=json.loads(dim) if isinstance(dim,str) else dim
            if name=='GA4 Channels':r.update(channel=dim.get('sessionDefaultChannelGroup',''),channel_scope='Session default channel group')
            if name=='GA4 Events':r['event_name']=dim.get('eventName','')
            # A successful collector replaces this partition. Until then preserve old measured values.
            rows.append(r)
        store.set(name,rows)
    store.set('Event Mapping',[{'business_action':'software_download','event_name':'software_download','language':'all','confirmed':True,
                              'meaning':'软件下载点击；不代表完成下载或安装','tracking_status':'awaiting_first_event','effective_from':'2026-09-09'}])
    inspection=[]
    for r in store.read('URL Inspection'):
        res=r.get('result',{});res=json.loads(res) if isinstance(res,str) else res;state=res.get('indexStatusResult',{})
        r={k:v for k,v in r.items() if k!='status'}
        r.update(api_status='success' if res else 'failed',verdict=state.get('verdict',''),coverage_state=state.get('coverageState',''),
                 last_crawl_time=state.get('lastCrawlTime',''),google_canonical=state.get('googleCanonical',''),user_canonical=state.get('userCanonical',''),
                 page_fetch_state=state.get('pageFetchState',''),inspection_link=res.get('inspectionResultLink',''));inspection.append(r)
    store.set('URL Inspection',inspection,headers=['url','api_status','verdict','coverage_state','last_crawl_time','google_canonical','user_canonical','page_fetch_state','checked_at','inspection_link','id','result'])
    # Keep all previous snapshot history in verified backup; seed compact history once.
    if any(not r.get('change') for r in store.read('Sitemap History')):
        store.set('Sitemap History',[{'id':digest(['baseline',r['id']]),'change':'baseline','url':r['url'],'sitemap':r.get('sitemap',''),'lastmod':r.get('lastmod',''),'observed_at':r.get('observed_at',stamp())} for r in store.read('Sitemap URLs')],headers=['change','url','sitemap','lastmod','previous_lastmod','observed_at','id'])
    registry(store)
    if not store.read('Comparisons'):store.set('Comparisons',[],headers=['source','language','period','comparison','current_start','current_end','baseline_start','baseline_end','metric','value','baseline','change_pct','change_pp','comparison_status','reason'])
    for name in ('Weekly Overview','Monthly Overview'):
        if not report.read(name):report.set(name,[{'section':'状态','item':'等待首个可用周期','value':'自动采集周期数据后生成；缺失日期不补零。'}],headers=['section','item','value','priority','source_link'])
    store.flush();report.flush()
    if retired:remove(store,retired)
    update_guide(store,report);store.flush()
    print(json.dumps({'migration':'v2','manual_urls':len(registry(store)),'consolidated':retired,'status':'success'}))

if __name__=='__main__':main()
