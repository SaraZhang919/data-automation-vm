import json
import re
from datetime import date, timedelta
from urllib.parse import quote
from .core import SITE, LANGS, LAUNCH, days, digest, language, mature, stamp
from .storage import request, ApiFailure

GA_METRICS=['sessions','activeUsers','totalUsers','newUsers','engagedSessions','engagementRate','averageSessionDuration','keyEvents']

def metric_changed(before,after,keys):
    for k in keys:
        a,b=before.get(k),after.get(k)
        try:
            if float(a)!=float(b):return True
        except (TypeError,ValueError):
            if a!=b:return True
    return False

class Analytics:
    def __init__(self, session): self.s=session; self.timezones={}

    def ga_timezone(self, pid):
        if pid not in self.timezones:
            _,meta=self.ga(pid,LAUNCH,'yesterday',[],['sessions'])
            if not meta.get('timeZone'):raise ApiFailure('GA timezone unavailable')
            self.timezones[pid]=meta['timeZone']
        return self.timezones[pid]

    def ga(self,pid,start,end,dimensions,metrics,filters=None):
        body={'dateRanges':[{'startDate':str(start),'endDate':str(end)}],
              'dimensions':[{'name':x} for x in dimensions], 'metrics':[{'name':x} for x in metrics],
              'limit':10000,'offset':0,'returnPropertyQuota':True}
        if filters: body['dimensionFilter']=filters
        rows=[]; meta={}
        while True:
            data=request(self.s,'POST',f'https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport',json=body).json()
            meta=data.get('metadata',{})
            for r in data.get('rows',[]):
                row={k:v['value'] for k,v in zip(dimensions,r.get('dimensionValues',[]))}
                row.update({k:float(v['value']) for k,v in zip(metrics,r.get('metricValues',[]))})
                rows.append(row)
            body['offset']+=len(data.get('rows',[]))
            if body['offset']>=data.get('rowCount',0): break
            if not data.get('rows'): raise ApiFailure('GA pagination stopped early')
        return rows,meta

    def gsc(self,start,end,dimensions,lang='all',state='final',exact='',prefix=''):
        filters=[]
        if lang != 'all':
            if lang=='en':
                filters.append({'dimension':'page','operator':'includingRegex','expression':r'^https://www\.iboomto\.com(/|$)'})
                filters.append({'dimension':'page','operator':'excludingRegex','expression':r'^https://www\.iboomto\.com/(ar|ja|zh-tw|es|de|fr|it|pt)(/|[?#]|$)'})
            else:
                filters.append({'dimension':'page','operator':'includingRegex','expression':rf'^https://www\.iboomto\.com/{lang}(/|[?#]|$)'})
        if exact: filters.append({'dimension':'page','operator':'equals','expression':exact})
        if prefix: filters.append({'dimension':'page','operator':'includingRegex','expression':'^'+re.escape(SITE+prefix)})
        body={'startDate':str(start),'endDate':str(end),'dimensions':dimensions,'dataState':state,'rowLimit':25000,'startRow':0,'type':'web'}
        if filters: body['dimensionFilterGroups']=[{'groupType':'and','filters':filters}]
        rows=[]; metadata={}; capped=False
        while True:
            data=request(self.s,'POST','https://www.googleapis.com/webmasters/v3/sites/'+quote('sc-domain:iboomto.com',safe='')+'/searchAnalytics/query',json=body).json()
            metadata.update(data.get('metadata',{}))
            batch=data.get('rows',[])
            for r in batch:
                row=dict(zip(dimensions,r.get('keys',[])))
                row.update({k:r[k] for k in ('clicks','impressions','ctr','position')})
                rows.append(row)
            if len(batch)<25000: break
            body['startRow']+=len(batch)
            if body['startRow']>=50000:
                capped=True; break
        return rows,metadata,capped

    def gsc_access(self):
        data=request(self.s,'GET','https://www.googleapis.com/webmasters/v3/sites').json()
        if not any(r['siteUrl']=='sc-domain:iboomto.com' for r in data.get('siteEntry',[])):
            raise ApiFailure('GSC sc-domain:iboomto.com not accessible')

    def inspection(self,url):
        r=self.s.post('https://searchconsole.googleapis.com/v1/urlInspection/index:inspect',json={'inspectionUrl':url,'siteUrl':'sc-domain:iboomto.com','languageCode':'en-US'},timeout=(10,20))
        if r.status_code!=200:raise ApiFailure(f'URL Inspection HTTP {r.status_code}')
        return r.json().get('inspectionResult',{})

def ga_filter(exact='',prefix=''):
    expr=[{'filter':{'fieldName':'hostName','stringFilter':{'matchType':'EXACT','value':'www.iboomto.com'}}}]
    if exact:
        expr.append({'filter':{'fieldName':'pageLocation','stringFilter':{'matchType':'EXACT','value':exact}}})
    if prefix:
        expr.append({'filter':{'fieldName':'pagePath','stringFilter':{'matchType':'BEGINS_WITH','value':prefix}}})
    return {'andGroup':{'expressions':expr}}

def ga_quality(meta,end,tz,now,start):
    if meta.get('subjectToThresholding') or meta.get('samplingMetadatas') or meta.get('dataLossFromOtherRow'):
        return 'limited'
    if start<LAUNCH: return 'partial_launch'
    return 'mature' if mature(end,tz,now) else 'provisional'

def collect_ga(api,store,prop,start,end,now,period='daily',exact='',prefix='',manual=False):
    if end<LAUNCH: return {'rows':0,'status':'prelaunch'}
    tz=api.ga_timezone(prop['id'])
    qstart=max(start,LAUNCH)
    tables=[('Daily',[],GA_METRICS),('Channels',['sessionDefaultChannelGroup'],GA_METRICS),
            ('Landing Pages',['landingPagePlusQueryString'],['sessions','activeUsers','totalUsers','engagementRate','keyEvents']),
            ('Events',['eventName'],['eventCount','totalUsers'])]
    result=[]
    for suffix,dims,metrics in tables:
        ds=(['date'] if period=='daily' else [])+dims
        rows,meta=api.ga(prop['id'],qstart,end,ds,metrics,ga_filter(exact,prefix))
        packed=[]
        for row in rows:
            d=date.fromisoformat(row.pop('date')) if period=='daily' else end
            rs=d if period=='daily' else start
            quality=ga_quality(meta,d,tz,now,rs)
            dimension={k:row.pop(k) for k in dims}
            if suffix=='Landing Pages':
                path=dimension['landingPagePlusQueryString']
                dimension['url']=SITE+path if path.startswith('/') else path
                dimension['url_language']=language(dimension['url']) or 'unknown'
            record={'source':'GA4','property':prop['id'],'language':prop['language'],'period':period,'start':str(rs),'end':str(d),
                    'timezone':tz,'quality':quality,'dimensions':json.dumps(dimension,ensure_ascii=False,sort_keys=True),
                    **row,'collected_at':stamp(),'metadata':meta,'scope':json.dumps({'exact':exact,'prefix':prefix},sort_keys=True)}
            if 'keyEvents' in row and 'totalUsers' in row:
                record['key_events_per_user']=row['keyEvents']/row['totalUsers'] if row['totalUsers'] else ''
            record['id']=digest([record[k] for k in ('source','property','period','start','end','dimensions','scope')]+[suffix])
            packed.append(record)
        tab='Manual Results' if manual else ('GA4 '+suffix if period=='daily' else f'GA4 {period.title()} '+suffix)
        if manual:
            for r in packed: r['view']=suffix
        # Clear just this successfully fetched partition, including disappeared detail rows.
        def partition(r):
            return str(r.get('property'))==prop['id'] and r.get('period')==period and str(qstart)<=r.get('end','')<=str(end) and r.get('scope')==json.dumps({'exact':exact,'prefix':prefix},sort_keys=True) and (not manual or r.get('view')==suffix)
        old={r['id']:r for r in store.read(tab) if 'id' in r}
        revisions=[]
        for r in packed:
            prior=old.get(r['id'])
            if prior and metric_changed(prior,r,metrics):
                revisions.append({'id':digest([r['id'],r['collected_at']]),'record_id':r['id'],'source':tab,'date':r['end'],'old_metrics':{k:prior.get(k) for k in metrics},'new_metrics':{k:r.get(k) for k in metrics},'revised_at':r['collected_at']})
        store.upsert('Data Revisions',revisions)
        store.upsert(tab,packed,replace_where=partition)
        result+=packed
    return {'rows':len(result),'timezone':tz,'status':ga_quality({},end,tz,now,start)}

def collect_business_events(api,store,prop,start,end,now):
    mappings=[r for r in store.read('Event Mapping') if str(r.get('confirmed','')).lower()=='true' and r.get('event_name') and r.get('language','all') in ('all',prop['language'])]
    tz=api.ga_timezone(prop['id']);records=[]
    groups={}
    for m in mappings:groups.setdefault(m['business_action'],set()).update(x.strip() for x in m['event_name'].split(',') if x.strip())
    totals={r['end']:r for r in store.read('GA4 Daily') if str(r.get('property'))==prop['id']}
    for action,names in groups.items():
        filters=ga_filter()
        filters['andGroup']['expressions'].append({'filter':{'fieldName':'eventName','inListFilter':{'values':sorted(names)}}})
        rows,meta=api.ga(prop['id'],max(start,LAUNCH),end,['date'],['eventCount','totalUsers'],filters)
        for row in rows:
            d=date.fromisoformat(row['date']);denom=totals.get(str(d),{}).get('totalUsers')
            record={'id':digest([prop['id'],str(d),action]),'property':prop['id'],'language':prop['language'],'start':str(d),'end':str(d),'action':action,
                    'event_names':sorted(names),'event_count':row['eventCount'],'converting_users':row['totalUsers'],'eligible_users':denom,
                    'user_conversion_rate':row['totalUsers']/denom if denom else '', 'quality':ga_quality(meta,d,tz,now,d),'timezone':tz,'collected_at':stamp()}
            records.append(record)
    store.upsert('GA4 Business Events',records)
    return {'status':'success' if mappings else 'not_configured','mapped_actions':list(groups),'rows':len(records)}

def collect_gsc(api,store,start,end,period='daily',lang='all',exact='',prefix='',manual=False):
    if end<LAUNCH:return {'rows':0,'status':'prelaunch'}
    qstart=max(start,LAUNCH)
    probe,meta,_=api.gsc(qstart,end,['date'],'all','all')
    final,_,_=api.gsc(qstart,end,['date'],'all','final')
    first_incomplete=meta.get('first_incomplete_date')
    # A nonzero finalized date proves publication through that date, not activity on every date.
    final_through=max((r['date'] for r in final),default='')
    if first_incomplete:
        final_through=max(final_through,str(date.fromisoformat(first_incomplete)-timedelta(days=1)))
    complete=bool(final_through and final_through>=str(end))
    total=0
    languages=LANGS+('all',) if lang=='all' else (lang,)
    for lg in languages:
        for suffix,dimensions in [('Daily',[]),('Pages',['page']),('Queries',['query'])]:
            dims=(['date'] if period=='daily' else [])+dimensions
            rows,_,capped=api.gsc(qstart,end,dims,lg,'all' if period=='daily' else 'final',exact,prefix)
            packed=[]
            for row in rows:
                d=row.pop('date') if period=='daily' else str(end)
                rs=d if period=='daily' else str(start)
                dim={k:row.pop(k) for k in dimensions}
                if 'page' in dim and language(dim['page']) is None:continue
                status='final' if final_through and d<=final_through else 'provisional'
                if start<LAUNCH and period!='daily': status='partial_launch'
                if capped:status='limited'
                rec={'source':'GSC','language':lg,'period':period,'start':rs,'end':d,'timezone':'America/Los_Angeles','quality':status,
                     'dimensions':json.dumps(dim,ensure_ascii=False,sort_keys=True),**row,'collected_at':stamp(),
                     'scope':json.dumps({'exact':exact,'prefix':prefix},sort_keys=True),'aggregation':'property' if lg=='all' and not exact and not prefix else 'page-filtered',
                     'coverage':'top_rows_not_exhaustive' if dimensions else 'aggregate','final_through':final_through}
                rec['id']=digest(['GSC',lg,period,rs,d,rec['dimensions'],rec['scope'],suffix])
                if manual:rec['view']=suffix
                packed.append(rec)
            tab='Manual Results' if manual else ('GSC '+suffix if period=='daily' else f'GSC {period.title()} '+suffix)
            scope=json.dumps({'exact':exact,'prefix':prefix},sort_keys=True)
            # Never replace an already finalized row with a newer provisional response.
            old={r.get('id'):r for r in store.read(tab)}
            for i,r in enumerate(packed):
                if old.get(r['id'],{}).get('quality')=='final' and r['quality']=='provisional': packed[i]=old[r['id']]
            revisions=[]
            for r in packed:
                before=old.get(r['id'])
                if before and metric_changed(before,r,('clicks','impressions','ctr','position')):
                    revisions.append({'id':digest([r['id'],r['collected_at']]),'record_id':r['id'],'source':tab,'date':r['end'],
                                      'old_metrics':{k:before.get(k) for k in ('clicks','impressions','ctr','position')},
                                      'new_metrics':{k:r.get(k) for k in ('clicks','impressions','ctr','position')},'revised_at':r['collected_at']})
            store.upsert('Data Revisions',revisions)
            # Replace only finalized, uncapped query partitions. Missing dates remain missing, not zero.
            def partition(r):
                return (not capped and bool(final_through) and r.get('source')=='GSC' and r.get('language')==lg and r.get('period')==period
                        and str(qstart)<=r.get('end','')<=min(str(end),final_through) and r.get('scope')==scope
                        and (not manual or r.get('view')==suffix))
            store.upsert(tab,packed,replace_where=partition)
            total+=len(packed)
    return {'rows':total,'final_through':final_through,'status':'final' if complete else 'pending'}
