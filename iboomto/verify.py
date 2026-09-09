"""Read-only acceptance checks; optionally remove representation-only test revisions."""
import argparse,json,os
from .core import DATA_ID,load_local_env,LANGS
from .storage import google_session,Sheets
from .analytics import metric_changed

def main():
    p=argparse.ArgumentParser();p.add_argument('--env-file');p.add_argument('--clean-test-revisions',action='store_true');args=p.parse_args()
    if args.env_file:load_local_env(args.env_file)
    s=google_session();data=Sheets(s,DATA_ID,args.clean_test_revisions)
    tables=['GA4 Daily','GA4 Channels','GA4 Landing Pages','GA4 Events','GSC Daily','GSC Pages','GSC Queries','SF Pages','SF Links Latest','SF Hreflang Latest','Sitemap URLs','Technical Checks','URL Inspection','Manual Results']
    result={}
    for name in tables:
        rows=data.read(name);ids=[r.get('id') for r in rows]
        result[name]={'rows':len(rows),'unique_ids':len(set(ids)),'duplicate_ids':len(ids)-len(set(ids))}
        if name=='GA4 Daily':result[name]['languages']=sorted({r['language'] for r in rows})
        if name=='URL Inspection':result[name]['statuses']={v:sum(r.get('status')==v for r in rows) for v in {r.get('status') for r in rows}}
    if args.clean_test_revisions:
        revisions=data.read('Data Revisions');keep=[]
        for r in revisions:
            a=r.get('old_metrics',{});b=r.get('new_metrics',{})
            if isinstance(a,str):a=json.loads(a)
            if isinstance(b,str):b=json.loads(b)
            if metric_changed(a,b,set(a)|set(b)):keep.append(r)
        data.set('Data Revisions',keep);data.flush()
        result['representation_only_revisions_removed']=len(revisions)-len(keep)
    rid=os.environ.get('IBOOMTO_REPORT_SHEET_ID')
    if rid:
        report=Sheets(s,rid)
        result['reports']=[{k:r.get(k) for k in ('report_date','kind','ai_status','summary')} for r in report.read('Daily History')]
        result['usage']=report.read('AI Usage')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
