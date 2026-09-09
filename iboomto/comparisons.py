"""Comparisons never fill missing baselines with zero or mix reporting periods."""
from datetime import date,timedelta
from .core import LAUNCH, RULE_VERSION, digest, count_alert, issue

SPECS={'GA4 Site':['sessions','activeUsers','engagementRate'], 'GSC Site':['clicks','impressions','ctr'],
       'GA4 Business Events':['event_count','converting_users','user_conversion_rate'],
       'GA4 Channels':['sessions'], 'GA4 Landing Pages':['sessions','activeUsers'], 'GSC Pages':['clicks','impressions','ctr']}
RATES={'ctr','engagementRate','user_conversion_rate'}

def baseline_range(cur,kind):
    start=date.fromisoformat(cur['start']);end=date.fromisoformat(cur['end'])
    if kind in ('day_over_day','same_weekday'):
        d=1 if kind=='day_over_day' else 7;return start-timedelta(days=d),end-timedelta(days=d)
    if cur['period']=='monthly':
        e=start-timedelta(days=1);return e.replace(day=1),e
    return start-(end-start)-timedelta(days=1),start-timedelta(days=1)

def compare(store):
    findings=[];out=[]
    rules=[tuple(float(r[k]) for k in ('min','max','yellow_pct','yellow_absolute','red_pct','red_absolute')) for r in store.read('Thresholds') if r['id'].startswith('counts-')]
    if len(rules)!=3:raise ValueError('Three count threshold tiers required')
    rate_rules={r['id']:r for r in store.read('Thresholds') if r['id'].startswith('rate-')}
    for tab,metrics in SPECS.items():
        groups={}
        for r in store.read(tab):
            if r.get('period') not in ('daily','weekly','monthly'):continue
            if not r.get('start') or not r.get('end'):continue
            k=(r.get('language',''),str(r.get('property','')),r.get('period'),r.get('channel',''),r.get('page_url',''),r.get('action',''),r.get('scope',''))
            groups.setdefault(k,{})[(r['start'],r['end'])]=r
        for key,items in groups.items():
            cur=max(items.values(),key=lambda r:r['end'])
            kinds=('day_over_day','same_weekday') if cur['period']=='daily' else (cur['period']+'_over_'+cur['period'],)
            for kind in kinds:
                bs,be=baseline_range(cur,kind);base=items.get((str(bs),str(be)),{})
                reason=''
                if bs<LAUNCH:reason='baseline_before_launch_or_partial_launch'
                elif not base:reason='baseline_missing'
                elif cur.get('quality') not in ('mature','final') or base.get('quality') not in ('mature','final'):reason='awaiting_mature_or_final_data'
                elif cur.get('scope_version','')!=base.get('scope_version',''):reason='scope_changed'
                for metric in metrics:
                    c=cur.get(metric);b=base.get(metric);why=reason
                    if not why and (c in ('',None) or b in ('',None)):why='metric_not_returned'
                    valid=not why;level='observe';change=ratio=pp=''
                    if valid:
                        c=float(c);b=float(b);change=c-b;ratio=change/b if b else '';pp=change*100 if metric in RATES else ''
                        if metric not in RATES:level=count_alert(c,b,'impressions' if metric=='impressions' else metric,rules)
                        else:
                            rule=rate_rules['rate-'+metric];denom='impressions' if metric=='ctr' else 'eligible_users' if metric=='user_conversion_rate' else 'sessions'
                            eligible=min(float(cur.get(denom) or 0),float(base.get(denom) or 0))>=float(rule['min_denominator'])
                            if metric=='user_conversion_rate':eligible &= float(base.get('converting_users') or 0)>=float(rule['min_converters'])
                            drop=b-c;relative=drop/b if b else 0
                            if eligible:level='red' if drop>=float(rule['red_points']) and relative>=float(rule['red_relative']) else 'yellow' if drop>=float(rule['yellow_points']) and relative>=float(rule['yellow_relative']) else 'normal'
                    rec={'id':digest([tab,key,kind,cur['start'],cur['end'],metric]),'source':tab,'language':key[0],'period':cur['period'],'comparison':kind,
                         'current_start':cur['start'],'current_end':cur['end'],'baseline_start':str(bs),'baseline_end':str(be),'metric':metric,
                         'page_url':cur.get('page_url',''),'channel':cur.get('channel',''),'value':c if c is not None else '', 'baseline':b if b is not None else '',
                         'change':change,'change_pct':ratio,'change_pp':pp,'comparison_status':'unavailable' if why else 'new_activity' if not b and c else 'comparable',
                         'reason':why,'severity':level,'rule_version':RULE_VERSION,'source_link':store.link(tab) if hasattr(store,'link') else ''}
                    out.append(rec)
                    if valid and level in ('yellow','red'):
                        findings.append(issue('metric_'+metric,cur.get('page_url') or tab+':'+key[0]+':'+cur.get('channel',''),level,rec,cur.get('collected_at',''),tab))
    headers=['source','language','period','comparison','current_start','current_end','baseline_start','baseline_end','metric','page_url','channel','value','baseline','change','change_pct','change_pp','comparison_status','reason','severity','source_link','id','rule_version']
    store.set('Comparisons',out,headers=headers)
    return findings
