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
            # Timezone metadata does not require scanning every day since launch.
            _,meta=self.ga(pid,'yesterday','yesterday',[],['sessions'])
            if not meta.get('timeZone'):raise ApiFailure('GA timezone unavailable')
            self.timezones[pid]=meta['timeZone']
        return self.timezones[pid]

    def ga(self,pid,start,end,dimensions,metrics,filters=None,limit=None,order=None):
        body={'dateRanges':[{'startDate':str(start),'endDate':str(end)}],
              'dimensions':[{'name':x} for x in dimensions], 'metrics':[{'name':x} for x in metrics],
              'limit':10000,'offset':0,'returnPropertyQuota':True}
        if filters: body['dimensionFilter']=filters
        if limit: body['limit']=limit
        if order: body['orderBys']=[{'metric':{'metricName':order},'desc':True}]
        rows=[]; meta={}
        while True:
            data=request(self.s,'POST',f'https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport',json=body).json()
            meta=data.get('metadata',{})
            for r in data.get('rows',[]):
                row={k:v['value'] for k,v in zip(dimensions,r.get('dimensionValues',[]))}
                row.update({k:float(v['value']) for k,v in zip(metrics,r.get('metricValues',[]))})
                rows.append(row)
            body['offset']+=len(data.get('rows',[]))
            if limit or body['offset']>=data.get('rowCount',0): break
            if not data.get('rows'): raise ApiFailure('GA pagination stopped early')
        return rows,meta

    def gsc(self,start,end,dimensions,lang='all',state='final',exact='',prefix='',limit=None):
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
        if limit: body['rowLimit']=limit
        rows=[]; metadata={}; capped=False
        while True:
            data=request(self.s,'POST','https://www.googleapis.com/webmasters/v3/sites/'+quote('sc-domain:iboomto.com',safe='')+'/searchAnalytics/query',json=body).json()
            metadata.update(data.get('metadata',{}))
            metadata['responseAggregationType']=data.get('responseAggregationType','unknown')
            batch=data.get('rows',[])
            for r in batch:
                row=dict(zip(dimensions,r.get('keys',[])))
                row.update({k:r[k] for k in ('clicks','impressions','ctr','position')})
                rows.append(row)
            if limit or len(batch)<25000: break
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
    if not mature(end,tz,now):return 'provisional'
    return 'partial_launch' if start<LAUNCH else 'mature'


from .collectors import collect_ga, collect_gsc, collect_business_events, collect_ai_traffic
