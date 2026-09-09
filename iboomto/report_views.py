"""Versioned reports with independently refreshed facts and period-specific views."""
import json
from .core import digest,stamp

def stable(value):
    if isinstance(value,dict):return {k:stable(v) for k,v in value.items() if k not in ('generated_at','collected_at','checked_at','observed_at','started_at','finished_at','updated_at','run_id','last_seen')}
    if isinstance(value,list):return [stable(v) for v in value]
    return value

def generate(store,report,statuses,issues,run_id,report_date,kind='daily',question='',force=False,selection=None):
    from .reporting import evidence,ai_analyse
    payload=evidence(store,statuses,issues,kind)
    if kind=='deep':
        from .core import select_url
        selection=selection or {};history=[]
        for tab in ('GA4 Site','GA4 Channels','GA4 Landing Pages','GA4 Events','GA4 Business Events','GSC Site','GSC Pages','GSC Queries'):
            for r in store.read(tab):
                if selection.get('start') and r.get('end','')<selection['start']:continue
                if selection.get('end') and r.get('start','')>selection['end']:continue
                if selection.get('language','all')!='all' and r.get('language')!=selection['language']:continue
                if selection.get('url') or selection.get('prefix'):
                    if not r.get('page_url') or not select_url(r['page_url'],selection.get('language','all'),selection.get('url',''),selection.get('prefix','')):continue
                history.append({**r,'table':tab})
        payload['selected_history']=history;payload['requested_selection']=selection
        payload['latest_metrics']=[];payload['detail_summaries']={};payload['comparisons']=[]
    period=payload['report_period'];name='Deep Analysis' if kind=='deep' else 'Report History'
    dates=sorted({(r['start'],r['end']) for r in payload['latest_metrics']})
    fingerprint=digest([stable(payload),kind,question,selection])
    rid=digest([str(report_date),kind,fingerprint])
    history=report.read(name)
    prior=next((r for r in history if r.get('id')==rid and r.get('ai_status')=='success'),None)
    state='success';cached=bool(prior and not force)
    if cached:
        analysis={k:prior.get(k,[] if k!='summary' else '') for k in ('summary','findings','actions','deep_analysis_candidates','limitations')}
        for k,v in list(analysis.items()):
            if k!='summary' and isinstance(v,str):
                try:analysis[k]=json.loads(v)
                except ValueError:analysis[k]=v.split('\n\n') if v else []
        record=prior
    else:
        try:analysis=ai_analyse(payload,report,kind,question,force)
        except Exception as exc:
            state='failed';analysis={'summary':'事实数据已更新；AI 分析未完成。','findings':[],'actions':[],'deep_analysis_candidates':[],'limitations':[str(exc)]}
        if force:rid=digest([rid,stamp(),run_id])
        version=1+sum(r.get('kind')==kind and r.get('report_date')==str(report_date) for r in history)
        record={'id':rid,'report_date':str(report_date),'kind':kind,'period':period,'statistical_ranges':dates,'version':version,
                'generated_at':stamp(),'run_id':run_id,'ai_status':state,'evidence_hash':fingerprint,'question':question,**analysis}
        report.upsert(name,[record])
    if kind!='deep':
        tab='Weekly Overview' if kind.startswith('weekly') else 'Monthly Overview' if kind=='monthly' else 'Overview'
        label='周报' if kind.startswith('weekly') else '月报' if kind=='monthly' else '日报'
        rows=[{'section':label,'item':'报告日期','value':str(report_date)},
              {'section':label,'item':'事实更新 UTC','value':stamp()},
              {'section':label,'item':'AI 分析 UTC','value':record['generated_at']},
              {'section':label,'item':'版本 / AI 状态','value':str(record.get('version',1))+' / '+record['ai_status']},
              {'section':'分析','item':'摘要','value':analysis['summary']}]
        for r in sorted(payload['issues'],key=lambda r:(r.get('priority','P3'),r.get('kind','')))[:40]:
            rows.append({'section':'待处理问题','item':r.get('kind'),'priority':r.get('priority','P3'),
                         'value':{'url':r.get('url'),'reason':r.get('priority_reason'),'evidence':r.get('evidence')},'source_link':r.get('source_link','')})
        for field,label in [('findings','发现'),('actions','建议行动'),('limitations','局限')]:
            for i,v in enumerate(analysis[field]):rows.append({'section':label,'item':i+1,'value':v})
        for r in payload['historical_coverage']:
            rows.append({'section':'数据覆盖核对','item':r['source'],'value':{'period':period,'latest':r['latest_dates'],'mature_or_final':r['latest_final_dates']},'source_link':r['source_link']})
        for r in payload['latest_metrics']:
            rows.append({'section':r['table'],'item':r['language']+' '+r['start']+' — '+r['end']+' '+r['quality'],
                         'value':{k:r[k] for k in ('sessions','activeUsers','clicks','impressions','ctr') if k in r},'source_link':store.link(r['table']) if hasattr(store,'link') else ''})
        for r in payload['detail_summaries'].get('GA4 Business Events',[]):
            rows.append({'section':'软件下载点击','item':r['language']+' '+r['start']+' — '+r['end'],
                         'value':{k:r.get(k) for k in ('event_count','converting_users','user_conversion_rate','data_status','quality')},
                         'source_link':store.link('GA4 Business Events') if hasattr(store,'link') else ''})
        report.set(tab,rows,headers=['section','item','value','priority','source_link'])
    report.upsert('Data Status',statuses)
    return {'status':'cached' if cached else state,'report_id':rid,'ai_status':record['ai_status'],'overview_refreshed':True}
