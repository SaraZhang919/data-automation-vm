"""Bounded page acquisition, explicit scopes and shared period schemas."""
import json
from datetime import date, timedelta
from urllib.parse import urlsplit
from .core import SITE, LANGS, LAUNCH, days, digest, stamp, language
from .pages import registry, page_fields, pure_url, selected_pages, TOP_PAGES, TOP_QUERIES

HOST='www.iboomto.com'
SCOPE_VERSION='production-host-v2'

def day(value):
    return date.fromisoformat(str(value))

def scope(exact='',prefix='',ga=False):
    return json.dumps({'exact':exact,'prefix':prefix,**({'hostname':HOST,'match':'EXACT','version':SCOPE_VERSION} if ga else {})},sort_keys=True)

def table(source,suffix):
    return source+' '+('Site' if suffix=='Daily' else suffix)

def append_filter(filters,field,values):
    filters['andGroup']['expressions'].append({'filter':{'fieldName':field,'inListFilter':{'values':sorted(values)}}})
    return filters

def previous_range(start,end,period):
    if period=='monthly':
        e=start-timedelta(days=1);return e.replace(day=1),e
    return start-(end-start)-timedelta(days=1),start-timedelta(days=1)

def save(store,tab,packed,partition,metrics):
    from .analytics import metric_changed
    if tab in ('GA4 Landing Pages','GSC Pages'):
        for row in packed:row.pop('subfolder',None)
    old={r.get('id'):r for r in store.read(tab)};revisions=[]
    for r in packed:
        before=old.get(r['id'])
        if before and metric_changed(before,r,metrics):
            revisions.append({'id':digest([r['id'],r['collected_at']]),'record_id':r['id'],'source':tab,'date':r['end'],
                'old_metrics':{k:before.get(k) for k in metrics},'new_metrics':{k:r.get(k) for k in metrics},'revised_at':r['collected_at']})
    store.upsert('Data Revisions',revisions)
    store.upsert(tab,packed,replace_where=partition)

def collect_ga(api,store,prop,start,end,now,period='daily',exact='',prefix='',manual=False):
    from .analytics import ga_filter,ga_quality,GA_METRICS
    if end<LAUNCH:return {'rows':0,'status':'prelaunch'}
    tz=api.ga_timezone(prop['id']);qstart=max(start,LAUNCH);pages=registry(store);lg=prop['language']
    scoped=scope(exact,prefix,True);total=0
    specs=[('Daily',[],GA_METRICS),('Channels',['sessionDefaultChannelGroup'],GA_METRICS),
           ('Landing Pages',['landingPage'],['sessions','activeUsers','totalUsers','engagementRate','keyEvents']),
           ('Events',['eventName'],['eventCount','totalUsers'])]
    for suffix,dims,metrics in specs:
        filters=ga_filter(exact,prefix);selected={}
        if suffix=='Landing Pages':
            # Rank a bounded organic landing-page pool, then fetch all-channel metrics for it.
            def top(rs,re):
                if re<LAUNCH:return []
                f=append_filter(ga_filter(),'sessionDefaultChannelGroup',['Organic Search'])
                ranked,_=api.ga(prop['id'],max(LAUNCH,rs),re,['landingPage'],['activeUsers'],f,limit=TOP_PAGES,order='activeUsers')
                return [SITE+r['landingPage'] for r in ranked if r['landingPage'].startswith('/')]
            ps,pe=previous_range(start,end,period)
            selected=selected_pages(top(qstart,end),pages,lg,top(ps,pe) if period!='daily' else ())
            if exact:selected={pure_url(exact):'manual_query'}
            if prefix:selected={u:v for u,v in selected.items() if urlsplit(u).path.startswith(prefix)}
            filters=ga_filter()
            rows=[];meta={}
            paths=[urlsplit(u).path for u in selected]
            for offset in range(0,len(paths),100):
                f=append_filter(ga_filter(),'landingPage',paths[offset:offset+100])
                batch,meta=api.ga(prop['id'],qstart,end,(['date'] if period=='daily' else [])+dims,metrics,f)
                rows+=batch
        else:
            rows,meta=api.ga(prop['id'],qstart,end,(['date'] if period=='daily' else [])+dims,metrics,filters)
        packed=[]
        for raw in rows:
            row=dict(raw);d=day(row.pop('date')) if period=='daily' else end;rs=d if period=='daily' else start
            dim={k:row.pop(k) for k in dims}
            rec={'source':'GA4','property':prop['id'],'language':lg,'period':period,'start':str(rs),'end':str(d),
                 'timezone':tz,'quality':ga_quality(meta,d,tz,now,rs),'data_status':'returned','dimensions':json.dumps(dim,sort_keys=True),
                 **row,'collected_at':stamp(),'metadata':meta,'scope':scoped,'hostname_filter':'hostName EXACT '+HOST,'scope_version':SCOPE_VERSION}
            if suffix=='Landing Pages':
                u=SITE+dim['landingPage'];rec.update(page_fields(u,pages));rec['selection_reason']=selected.get(u,'selected')
            if suffix=='Channels':rec.update(channel=dim['sessionDefaultChannelGroup'],channel_scope='Session default channel group')
            if suffix=='Events':rec['event_name']=dim['eventName']
            if 'keyEvents' in row:rec['key_events_per_user']=row['keyEvents']/row['totalUsers'] if row['totalUsers'] else ''
            rec['id']=digest(['GA4',prop['id'],period,str(rs),str(d),dim,scoped,suffix]);packed.append(rec)
        if suffix=='Landing Pages':
            present={(r['end'],r['page_url']) for r in packed}
            for d in (days(qstart,end) if period=='daily' else [end]):
                for u,reason in selected.items():
                    if (str(d),u) in present:continue
                    rs=d if period=='daily' else start;dim={'landingPage':urlsplit(u).path}
                    packed.append({'id':digest(['GA4',prop['id'],period,str(rs),str(d),dim,scoped,suffix]),'source':'GA4','property':prop['id'],'language':lg,
                        'period':period,'start':str(rs),'end':str(d),'timezone':tz,'quality':ga_quality(meta,d,tz,now,rs),
                        'data_status':'no_data_returned','scope':scoped,'hostname_filter':'hostName EXACT '+HOST,'scope_version':SCOPE_VERSION,
                        'dimensions':json.dumps(dim,sort_keys=True),**page_fields(u,pages),'selection_reason':reason,'collected_at':stamp()})
        tab='Manual Results' if manual else table('GA4',suffix)
        if manual:
            for r in packed:r['view']=suffix
        def partition(r):
            return str(r.get('property'))==prop['id'] and r.get('period')==period and str(qstart)<=r.get('end','')<=str(end) and r.get('scope')==scoped and (not manual or r.get('view')==suffix)
        save(store,tab,packed,partition,metrics);total+=len(packed)
    if not manual:
        site={r['end']:r for r in store.read('GA4 Site') if str(r.get('property'))==prop['id'] and r.get('period')==period and str(qstart)<=r.get('end','')<=str(end)}
        sums={}
        for r in store.read('GA4 Channels'):
            if str(r.get('property'))==prop['id'] and r.get('period')==period and r['end'] in site:sums[r['end']]=sums.get(r['end'],0)+float(r.get('sessions') or 0)
        store.upsert('GA4 Data Quality',[{'id':digest([prop['id'],period,d,'channel_sum']),'property':prop['id'],'language':lg,'period':period,'start':site[d]['start'],'end':d,
            'api_sessions':site[d].get('sessions'),'channel_rows_sum':value,'status':'matches' if value==site[d].get('sessions') else 'non_additive_review',
            'meaning':'Use API site total; do not sum or rescale channel rows. Cause not established.','checked_at':stamp()} for d,value in sums.items()])
    return {'rows':total,'timezone':tz,'status':ga_quality({},end,tz,now,start)}

def collect_business_events(api,store,prop,start,end,now,period='daily'):
    from .analytics import ga_filter,ga_quality
    if end<LAUNCH:return {'status':'prelaunch','rows':0}
    tz=api.ga_timezone(prop['id']);qstart=max(start,LAUNCH)
    mappings=[r for r in store.read('Event Mapping') if str(r.get('confirmed','')).lower()=='true' and r.get('event_name')=='software_download' and r.get('language','all') in ('all',prop['language'])]
    if not mappings:return {'status':'not_configured','rows':0}
    f=append_filter(ga_filter(),'eventName',['software_download'])
    rows,meta=api.ga(prop['id'],qstart,end,['date'] if period=='daily' else [],['eventCount','totalUsers'],f)
    observed={str(day(r['date'])) if period=='daily' else str(end):r for r in rows}
    totals={r['end']:r for r in store.read('GA4 Site') if str(r.get('property'))==prop['id'] and r.get('period')==period}
    records=[]
    for d in (days(qstart,end) if period=='daily' else [end]):
        r=observed.get(str(d),{});denom=totals.get(str(d),{}).get('totalUsers');rs=d if period=='daily' else start
        records.append({'id':digest([prop['id'],period,str(rs),str(d),'software_download']),'property':prop['id'],'language':prop['language'],
            'period':period,'start':str(rs),'end':str(d),'action':'software_download','event_name':'software_download',
            'event_count':r.get('eventCount',''),'converting_users':r.get('totalUsers',''),'eligible_users':denom,
            'user_conversion_rate':r['totalUsers']/denom if r and denom else '',
            'data_status':'returned' if r else 'waiting_for_event_data','quality':ga_quality(meta,d,tz,now,rs),'timezone':tz,
            'hostname_filter':'hostName EXACT '+HOST,'scope_version':SCOPE_VERSION,'collected_at':stamp()})
    store.upsert('GA4 Business Events',records)
    return {'status':'success' if rows else 'waiting_for_event_data','rows':len(records),'event_name':'software_download'}

def collect_gsc(api,store,start,end,period='daily',lang='all',exact='',prefix='',manual=False):
    if end<LAUNCH:return {'rows':0,'status':'prelaunch'}
    qstart=max(start,LAUNCH);pages=registry(store)
    # Probe beyond launch to recover Google's actual publication boundary, even before any launch-day final rows exist.
    _,meta,_=api.gsc(qstart-timedelta(days=7),end,['date'],'all','all')
    finals,_,_=api.gsc(qstart-timedelta(days=7),end,['date'],'all','final')
    incomplete=meta.get('firstIncompleteDate') or meta.get('first_incomplete_date')
    through=max((r['date'] for r in finals),default='')
    if incomplete:through=max(through,str(day(incomplete)-timedelta(days=1)))
    state='all' if period=='daily' else 'final';scoped=scope(exact,prefix);total=0
    for lg in (LANGS+('all',) if lang=='all' else (lang,)):
        for suffix,dimensions in [('Daily',[]),('Pages',['page']),('Queries',['query'])]:
            if lg=='all' and dimensions:continue
            dims=(['date'] if period=='daily' else [])+dimensions;selected={};capped=False;rows=[];info={}
            if suffix=='Pages':
                def top(rs,re):
                    if re<LAUNCH:return []
                    ranked,_,_=api.gsc(max(LAUNCH,rs),re,['page'],lg,state,limit=TOP_PAGES)
                    return [r['page'] for r in ranked]
                ps,pe=previous_range(start,end,period)
                selected=selected_pages(top(qstart,end),pages,lg,top(ps,pe) if period!='daily' else ())
                if exact:selected={pure_url(exact):'manual_query'}
                if prefix:selected={u:v for u,v in selected.items() if urlsplit(u).path.startswith(prefix)}
                for u in selected:
                    batch,info,cap=api.gsc(qstart,end,dims,lg,state,u);rows+=batch;capped|=cap
            elif suffix=='Queries' and period=='daily':
                # Per-day Top100: never request an unbounded date x query history.
                for d in days(qstart,end):
                    # Without the date dimension GSC sorts by clicks, not date/tied arbitrary order.
                    batch,info,cap=api.gsc(d,d,['query'],lg,state,exact,prefix,limit=TOP_QUERIES)
                    rows.extend({**r,'date':str(d)} for r in batch);capped|=cap
            else:
                rows,info,capped=api.gsc(qstart,end,dims,lg,state,exact,prefix,limit=TOP_QUERIES if suffix=='Queries' else None)
            packed=[]
            def quality(d):
                if capped:return 'limited'
                if start<LAUNCH and period!='daily':return 'partial_launch'
                return 'final' if through and str(d)<=through else 'provisional'
            for raw in rows:
                row=dict(raw);d=row.pop('date') if period=='daily' else str(end);rs=d if period=='daily' else str(start)
                dim={k:row.pop(k) for k in dimensions}
                rec={'source':'GSC','language':lg,'period':period,'start':rs,'end':d,'timezone':'America/Los_Angeles','quality':quality(d),
                     'data_status':'returned','dimensions':json.dumps(dim,sort_keys=True),**row,'collected_at':stamp(),'scope':scoped,
                     'aggregation':info.get('responseAggregationType','unknown'),'coverage':'selected_rows_not_exhaustive' if dimensions else 'api_aggregate',
                     'final_through':through,'first_incomplete_date':incomplete or ''}
                if suffix=='Pages':rec.update(page_fields(dim['page'],pages));rec.update(original_url=dim['page'],selection_reason=selected.get(pure_url(dim['page']),'selected'))
                if suffix=='Queries':rec.update(query=dim['query'],selection_reason='top100_clicks')
                rec['id']=digest(['GSC',lg,period,rs,d,rec['dimensions'],scoped,suffix]);packed.append(rec)
            if suffix=='Pages':
                present={(r['end'],r['page_url']) for r in packed}
                for d in (days(qstart,end) if period=='daily' else [end]):
                    for u,reason in selected.items():
                        if (str(d),u) in present:continue
                        rs=str(d) if period=='daily' else str(start);dim=json.dumps({'page':u},sort_keys=True)
                        packed.append({'id':digest(['GSC',lg,period,rs,str(d),dim,scoped,suffix]),'source':'GSC','language':lg,'period':period,
                            'start':rs,'end':str(d),'timezone':'America/Los_Angeles','quality':quality(d),'data_status':'no_data_returned',
                            'dimensions':dim,**page_fields(u,pages),'original_url':u,'selection_reason':reason,'scope':scoped,
                            'final_through':through,'first_incomplete_date':incomplete or '','collected_at':stamp(),'aggregation':'byPage'})
            tab='Manual Results' if manual else table('GSC',suffix)
            if manual:
                for r in packed:r['view']=suffix
            old={r.get('id'):r for r in store.read(tab)}
            for i,r in enumerate(packed):
                if old.get(r['id'],{}).get('quality')=='final' and r['quality']=='provisional':packed[i]=old[r['id']]
            def partition(r):
                return (not capped and r.get('source')=='GSC' and r.get('language')==lg and r.get('period')==period
                    and str(qstart)<=r.get('end','')<=str(end) and r.get('scope')==scoped
                    and (r.get('quality')!='final' or bool(through) and r.get('end','')<=through) and (not manual or r.get('view')==suffix))
            save(store,tab,packed,partition,('clicks','impressions','ctr','position'));total+=len(packed)
    return {'rows':total,'final_through':through,'first_incomplete_date':incomplete or '',
            'status':'partial_launch' if start<LAUNCH and through>=str(end) else 'final' if through>=str(end) else 'pending'}
