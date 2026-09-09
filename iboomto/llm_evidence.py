"""A compact analytical view, separate from the complete Sheets records.

No collection limits or token spending caps: this removes repeated storage fields,
groups unavailable comparisons, and summarizes the Clarity API's aggregate rows.
"""
import json
from collections import defaultdict
from urllib.parse import urlsplit,urlunsplit

SCHEMA='iboomto-analysis-v3'
DROP={'id','record_id','property','dimensions','metadata','scope','scope_version','collected_at','checked_at',
      'observed_at','updated_at','generated_at','started_at','finished_at','run_id','source_link','inspection_link',
      'first_seen','last_seen','resolved_at','priority_reason','hostname_filter','raw_hashes','folder','batch'}

def clean(value,key=''):
    if isinstance(value,dict):
        return {k:clean(v,k) for k,v in value.items() if k not in DROP and v not in ('',None)}
    if isinstance(value,list):return [clean(v,key) for v in value]
    if isinstance(value,str):
        if key in ('evidence','detail','data'):
            try:return clean(json.loads(value),key)
            except (ValueError,TypeError):pass
        if value.startswith(('https://','http://')):
            p=urlsplit(value);return urlunsplit((p.scheme,p.netloc,p.path,'',''))
    return value

def table(rows):
    """Lossless columnar encoding of selected analytical fields; no row truncation."""
    rows=[clean(r) for r in rows]
    if not rows:return {'count':0,'columns':[],'rows':[]}
    keys=list(dict.fromkeys(k for r in rows for k in r))
    common={k:rows[0][k] for k in keys if k in rows[0] and all(k in r and r[k]==rows[0][k] for r in rows)}
    columns=[k for k in keys if k not in common]
    return {'count':len(rows),'common':common,'columns':columns,'rows':[[r.get(k) for k in columns] for r in rows]}

def comparison_summary(rows):
    available=[];missing=defaultdict(lambda:{'row_count':0,'languages':set(),'metrics':set()})
    fields=('source','period','comparison','current_start','current_end','baseline_start','baseline_end','reason')
    for r in rows:
        if r.get('comparison_status')!='unavailable':available.append(r);continue
        group=missing[tuple(r.get(k,'') for k in fields)];group['row_count']+=1
        group['languages'].add(r.get('language',''));group['metrics'].add(r.get('metric',''))
    groups=[{**dict(zip(fields,key)),**{k:sorted(v) if isinstance(v,set) else v for k,v in counts.items()}} for key,counts in sorted(missing.items())]
    return {'available':table(available),'unavailable_groups':table(groups),
            'note':'Unavailable groups count comparison rows, not affected sessions/pages. Missing baselines are never treated as zero.'}

def clarity_summary(rows,period):
    if not rows:return {'status':'unavailable'}
    if any('view' in r for r in rows):
        from .clarity_summary import from_legacy
        rows=from_legacy(rows)
    if not rows:return {'status':'unavailable'}
    latest=max(rows,key=lambda r:r.get('window_end',''))
    return {'snapshot':clean(latest),'context_only':period!='daily',
            'notes':['One project-wide aggregate snapshot; no URL/device breakdown, recording or individual event stream.',
                     'Weekly collection covers the prior 72 hours (API maximum), NOT a full calendar week. Legacy snapshots keep their original 24-hour label.',
                     'Clarity project includes all tracked hosts; do not equate it with production-host-filtered GA.',
                     'Missing fields remain unknown, not zero. Session rates/scroll depth use fractions (0–1).']}


def compact_evidence(payload):
    if payload.get('_compact_schema'):return payload
    details={}
    for name,rows in payload.get('detail_summaries',{}).items():
        if name=='tracking_checks':continue # Business-event rows already carry the same status.
        details[name]=table(rows)
    # Business Events contains exact event counts and deduplicated users; do not double count its copy in GA4 Events.
    if details.get('GA4 Business Events',{}).get('count'):details.pop('GA4 Events',None)
    quality=payload.get('ga_data_quality',[])
    newest=max((r.get('end','') for r in quality),default='')
    return {'_compact_schema':SCHEMA,'report_period':payload.get('report_period'),
            'scope':'GA hostName EXACT www.iboomto.com; language denotes separate GA property. Dates/timezone and quality remain per source.',
            'data_status':table([r for r in payload.get('data_status',[]) if 'Report' not in r.get('source','')]),
            'coverage':clean(payload.get('historical_coverage',[])),
            'site_metrics':table(payload.get('latest_metrics',[])),
            'details':details,'comparisons':comparison_summary(payload.get('comparisons',[])),
            'issues':table([{**r,'issue_id':r.get('id','')} for r in payload.get('issues',[])]),'event_mapping':table(payload.get('event_mapping',[])),
            'ga_data_quality':table([r for r in quality if r.get('end')==newest]),
            'sf_batches':table(payload.get('sf_batches',[])),
            'clarity':clarity_summary(payload.get('clarity',[]),payload.get('report_period')),
            'period_status':table(payload.get('period_status',[])),
            'rules':table([{**r,'rule_name':r.get('id','')} for r in payload.get('rules',[])]),'limitations':payload.get('limitations',[]),
            **({'requested_selection':clean(payload['requested_selection']),
                'selected_history':table(payload.get('selected_history',[]))} if 'requested_selection' in payload else {})}

def dumps(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))

def evidence_chunks(payload,limit=150000):
    """Split oversized dictionaries AND tables without silently dropping nested evidence."""
    def sections(value,path=()):
        if len(dumps(value))<limit//2:
            yield {'path':list(path),'value':value};return
        if isinstance(value,dict) and 'columns' in value and 'rows' in value:
            template={k:v for k,v in value.items() if k not in ('rows','count')}
            for i,row in enumerate(value['rows']):yield {'path':list(path),'table':template,'row_index':i,'row':row}
        elif isinstance(value,dict):
            for k,v in value.items():yield from sections(v,path+(k,))
        elif isinstance(value,list):
            for i,v in enumerate(value):yield from sections(v,path+(i,))
        else:raise ValueError('One evidence field exceeds context safety boundary; split it at source')
    batch=[];size=0
    for part in sections(payload):
        n=len(dumps(part))
        if n>limit:raise ValueError('One evidence record exceeds context safety boundary')
        if batch and size+n>limit:yield batch;batch=[];size=0
        batch.append(part);size+=n
    if batch:yield batch
