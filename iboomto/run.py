import argparse
import json
import os
import sys
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .core import DATA_ID,LAUNCH,SITE,LANGS,digest,stamp,load_local_env,parse_properties,daily_window,previous_week,previous_month,language
from .storage import google_session,Sheets
from .analytics import Analytics,collect_ga,collect_gsc
from .technical import PublicSite,sitemap_collect,check_pages,sf_import,clarity_collect
from .reporting import initialise_config,metric_findings,reconcile_issues,generate_report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['daily','weekly-preview','monthly','manual','deep'],default='daily')
    p.add_argument('--env-file');p.add_argument('--write',action='store_true');p.add_argument('--no-ai',action='store_true')
    p.add_argument('--start');p.add_argument('--end');p.add_argument('--language',choices=['all',*LANGS],default='all')
    p.add_argument('--source',choices=['all','ga','gsc','technical','sf','clarity'],default='all')
    p.add_argument('--url',default='');p.add_argument('--prefix',default='');p.add_argument('--question',default='');p.add_argument('--force',action='store_true')
    p.add_argument('--output',default='runtime/latest.json')
    args=p.parse_args()
    if args.env_file:load_local_env(args.env_file)
    if args.mode=='manual' and (not args.start or not args.end):p.error('manual requires --start and --end')
    if args.start and args.end and args.start>args.end:p.error('start must not exceed end')
    if args.url and language(args.url) is None:p.error('URL must be an iBoomto content URL')
    if args.prefix and not args.prefix.startswith('/'):p.error('prefix must start with /')
    if args.no_ai:os.environ.pop('OPENAI_API_KEY',None)
    now=datetime.now(timezone.utc);today=now.astimezone(ZoneInfo('Asia/Tokyo')).date()
    run_id=os.environ.get('GITHUB_RUN_ID',digest([stamp(),args.mode]));statuses=[];findings=[];checked=set()
    session=google_session();store=Sheets(session,os.environ.get('IBOOMTO_SHEET_ID',DATA_ID),args.write)
    report_id=os.environ.get('IBOOMTO_REPORT_SHEET_ID')
    report=Sheets(session,report_id,args.write) if report_id else None
    props=parse_properties(store.read('Properties'));api=Analytics(session)
    initialise_config(store)

    def task(name,fn):
        started=stamp()
        try:
            result=fn() or {};status=result.get('status','success')
            detail=result
        except Exception as exc:
            status='failed';detail={'error_type':type(exc).__name__,'message':str(exc) if type(exc).__name__ in ('ApiFailure','ValueError') else 'See local diagnostics'}
        row={'id':name,'source':name,'status':status,'started_at':started,'finished_at':stamp(),'run_id':run_id,'detail':detail}
        statuses.append(row);store.upsert('Run Status',[{**row,'id':digest([run_id,name])}])
        print(json.dumps({'source':name,'status':status},ensure_ascii=False),flush=True)
        return status

    def period(source,start,end,kind,preview=False):
        if end<LAUNCH:return
        group=props if source=='GA4' else [{'language':'all','id':'GSC'}]
        for prop in group:
            key=digest([source,prop['id'],str(start),str(end),kind])
            prior=next((r for r in store.read('Period Status') if r.get('id')==key),None)
            if prior and prior.get('status') in ('final','mature','partial_launch') and not args.force:continue
            store.upsert('Period Status',[{'id':key,'source':source,'property':prop['id'],'period':kind,'start':str(start),'end':str(end),'status':'pending','updated_at':stamp()}])
            def run_period(prop=prop,key=key):
                result=collect_ga(api,store,prop,start,end,now,kind) if source=='GA4' else collect_gsc(api,store,start,end,kind)
                store.upsert('Period Status',[{'id':key,'source':source,'property':prop['id'],'period':kind,'start':str(start),'end':str(end),'status':result['status'],'updated_at':stamp()}])
                return result
            task(source+' '+kind+' '+prop['language'],run_period)

    if args.mode=='manual':
        start=date.fromisoformat(args.start);end=date.fromisoformat(args.end)
        for prop in props:
            if args.source in ('all','ga') and args.language in ('all',prop['language']):
                task('Manual GA4 '+prop['language'],lambda prop=prop:collect_ga(api,store,prop,start,end,now,'manual',args.url,args.prefix,True))
        if args.source in ('all','gsc'):
            task('Manual GSC',lambda:collect_gsc(api,store,start,end,'manual',args.language,args.url,args.prefix,True))
    elif args.mode!='deep':
        if args.mode=='daily':
            if args.source in ('all','ga'):
                for prop in props:
                    if args.language not in ('all',prop['language']):continue
                    def ga_job(prop=prop):
                        start,end=daily_window(now,api.ga_timezone(prop['id']))
                        if args.start:start=max(LAUNCH,date.fromisoformat(args.start))
                        if args.end:end=date.fromisoformat(args.end)
                        return collect_ga(api,store,prop,start,end,now)
                    task('GA4 '+prop['language'],ga_job)
            if args.source in ('all','gsc'):
                def gsc_job():
                    api.gsc_access();start,end=daily_window(now,'America/Los_Angeles')
                    return collect_gsc(api,store,date.fromisoformat(args.start) if args.start else start,date.fromisoformat(args.end) if args.end else end,lang=args.language)
                task('GSC',gsc_job)
            if args.source in ('all','sf'):
                def sf_job():
                    items,status=sf_import(session,store,now);findings.extend(items);return status
                task('Screaming Frog',sf_job)
            if args.source in ('all','technical'):
                web=PublicSite();sitemap_urls=[]
                def sitemap_job():
                    urls,complete=sitemap_collect(store,web);sitemap_urls.extend(urls)
                    return {'status':'success' if complete else 'partial','urls':len(urls)}
                task('Sitemap',sitemap_job)
                def checks_job():
                    items,successful=check_pages(store,web,sitemap_urls,now);findings.extend(items);checked.update(successful)
                    return {'status':'success','checked':len(successful)}
                task('Technical checks',checks_job)
                def inspect_job():
                    old={r['url']:r for r in store.read('URL Inspection')}
                    priority={r['url'] for r in store.read('Priority Pages') if r.get('enabled') not in (False,'FALSE','false')}
                    urls=sorted({r['url'] for r in sitemap_urls},key=lambda u:(u not in priority,u in old,old.get(u,{}).get('checked_at',''),u))[:100]
                    records=[];failed=0
                    for u in urls:
                        try:
                            result=api.inspection(u)
                            records.append({'id':u,'url':u,'checked_at':stamp(),'status':'success','result':result})
                        except Exception:failed+=1
                    store.upsert('URL Inspection',records)
                    return {'status':'partial' if failed else 'success','checked':len(records),'failed':failed}
                task('URL Inspection',inspect_job)
            if args.source in ('all','clarity'):
                task('Clarity',lambda:clarity_collect(store,os.environ.get('CLARITY_API_TOKEN'),now))
            # Period refreshes are source-independent and retry pending periods on daily runs.
            if args.source=='all':
                start,end=previous_week(today)
                if today.weekday() in (1,2,3,4,5):
                    period('GA4',start,end,'weekly');period('GSC',start,end,'weekly')
                if today.day>=4:
                    start,end=previous_month(today)
                    period('GA4',start,end,'monthly');period('GSC',start,end,'monthly')
                pending=list(store.read('Period Status'))
                for r in pending:
                    if r.get('status') not in ('mature','final','partial_launch'):
                        period(r['source'],date.fromisoformat(r['start']),date.fromisoformat(r['end']),r['period'])
        if args.mode=='weekly-preview':
            start,end=previous_week(today);period('GA4',start,end,'weekly',True)
        if args.mode=='monthly':
            start,end=previous_month(today);period('GA4',start,end,'monthly');period('GSC',start,end,'monthly')
    if args.mode not in ('manual','deep'):
        task('Website logs',lambda:{'status':'not_configured','detail':'Awaiting website access-log archive; installer logs excluded'})
    store.flush()
    if report:
        findings.extend(metric_findings(store))
        issues=reconcile_issues(report,findings,checked)
        kind={'weekly-preview':'weekly_preview','monthly':'monthly','deep':'deep'}.get(args.mode,'daily')
        if args.mode!='manual':
            task('Report',lambda:generate_report(store,report,statuses,issues,run_id,today,kind,args.question,args.force))
        report.upsert('Data Status',statuses);report.flush()
    elif args.mode!='manual':task('Report',lambda:{'status':'not_configured','detail':'IBOOMTO_REPORT_SHEET_ID missing'})
    store.flush()
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'run_id':run_id,'mode':args.mode,'statuses':statuses,'tables':{k:len(v) for k,v in store.cache.items()}},ensure_ascii=False,indent=2),encoding='utf-8')
    if any(s['status']=='failed' for s in statuses):sys.exit(1)

if __name__=='__main__':main()
