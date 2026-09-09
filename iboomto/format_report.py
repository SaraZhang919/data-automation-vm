"""Refresh formatting and add factual coverage without rewriting issued AI text."""
import json
from .core import DATA_ID,load_local_env
from .storage import google_session,Sheets
load_local_env('../.env.local')
s=google_session();data=Sheets(s,DATA_ID);report=Sheets(s,'15jBCSt2FqujGjm-L8-PFZTpkMCSDtJVKDl1rEANNNKU',True)
coverage=[]
for tab in ('GA4 Site','GSC Site'):
    dates=sorted({r['end'] for r in data.read(tab)})
    if dates:coverage.append({'section':'数据覆盖核对','item':tab,'value':f'源表已保存 {dates[0]} 至 {dates[-1]}，共 {len(dates)} 个日期；最新日期的预览不代表全部历史记录。'})
overview=[r for r in report.read('Overview') if r.get('section')!='数据覆盖核对']
report.set('Overview',overview[:3]+coverage+overview[3:])
for tab in ('Report History','Issues','Data Status','Deep Analysis','AI Usage'):
    rows=report.read(tab)
    for row in rows:
        for key in ('findings','actions','limitations','deep_analysis_candidates'):
            value=row.get(key)
            if isinstance(value,str) and value.startswith('['):
                try:row[key]=json.loads(value)
                except ValueError:pass
    report.set(tab,rows);report.dirty.add(tab)
report.read('AI Cache');report.dirty.add('AI Cache')
report.flush()
print('Report formatting refreshed; issued AI text and historical rows retained')
