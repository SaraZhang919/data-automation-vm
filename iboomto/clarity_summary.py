"""One project-wide snapshot per weekly Clarity request; no URL/device rows."""
import json
from .core import digest

FRICTION={'DeadClickCount':'dead_click','RageClickCount':'rage_click','ErrorClickCount':'error_click',
          'ScriptErrorCount':'script_error','QuickbackClick':'quickback_click','ExcessiveScroll':'excessive_scroll'}
CORE=set(FRICTION)|{'Traffic','EngagementTime','ScrollDepth'}

def numeric(value):
    if value in ('',None):return ''
    try:return float(value)
    except (ValueError,TypeError):return ''

def flatten(metrics,context):
    row={**context,'scope':'Clarity project all hosts','cadence':'weekly','is_full_calendar_week':False}
    for name,info in metrics.items():
        if name in FRICTION:
            prefix=FRICTION[name]
            row[prefix+'_count']=numeric(info.get('subTotal'))
            rate=numeric(info.get('sessionsWithMetricPercentage'))
            row[prefix+'_session_rate']=rate/100 if rate!='' else ''
            row[prefix+'_sessions_base']=numeric(info.get('sessionsCount'))
        elif name=='Traffic':
            for source,target in [('totalSessionCount','total_sessions'),('totalBotSessionCount','total_bot_sessions'),('distinctUserCount','distinct_users'),('pagesPerSessionPercentage','pages_per_session')]:
                row[target]=numeric(info.get(source))
            if row.get('distinct_users')=='':row['distinct_users']=numeric(info.get('distantUserCount'))
        elif name=='EngagementTime':row.update(active_time=numeric(info.get('activeTime')),total_time=numeric(info.get('totalTime')))
        elif name=='ScrollDepth':
            value=numeric(info.get('averageScrollDepth'));row['average_scroll_depth']=value/100 if value!='' else ''
    row['missing_metrics']=sorted(CORE-set(metrics));return row

def from_legacy(rows):
    snapshots={}
    for r in rows:
        if r.get('view')!='overall' or r.get('metric') not in CORE:continue
        key=(r.get('window_start'),r.get('window_end'));metrics,context=snapshots.setdefault(key,({},
            {'id':digest(['clarity_snapshot',*key]),'day':r.get('day'),'window_start':key[0],'window_end':key[1],
             'window_type':r.get('window_type'),'timezone':r.get('timezone'),'coverage':r.get('coverage'),'collected_at':r.get('collected_at')}))
        info=r.get('data',{});metrics[r['metric']]=json.loads(info) if isinstance(info,str) else info
    return [flatten(metrics,context) for metrics,context in snapshots.values()]
