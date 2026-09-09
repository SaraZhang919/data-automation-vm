import argparse,json,os
from .core import DATA_ID,MODEL,load_local_env,parse_properties
from .storage import google_session,Sheets,request
from .analytics import Analytics
from .technical import drive_list

def main():
    p=argparse.ArgumentParser();p.add_argument('--env-file');args=p.parse_args()
    if args.env_file:load_local_env(args.env_file)
    s=google_session();store=Sheets(s,DATA_ID);props=parse_properties(store.read('Properties'));api=Analytics(s)
    results=[]
    for prop in props:
        try:
            tz=api.ga_timezone(prop['id'])
            events,_=api.ga(prop['id'],'2026-09-07','yesterday',['eventName'],['eventCount'])
            results.append({'source':'GA4','language':prop['language'],'property':prop['id'],'timezone':tz,'events':events,'status':'success'})
        except Exception as e:results.append({'source':'GA4','language':prop['language'],'status':'failed','error':str(e)})
    try:api.gsc_access();results.append({'source':'GSC','status':'success'})
    except Exception as e:results.append({'source':'GSC','status':'failed','error':str(e)})
    try:
        from .core import SF_FOLDER
        results.append({'source':'Drive','folders':len(drive_list(s,SF_FOLDER)),'status':'success'})
    except Exception as e:results.append({'source':'Drive','status':'failed','error':str(e)})
    key=os.environ.get('OPENAI_API_KEY')
    if key:
        import requests
        try:
            r=requests.get('https://api.openai.com/v1/models/'+MODEL,headers={'Authorization':'Bearer '+key},timeout=30)
            results.append({'source':'OpenAI','model':MODEL,'status':r.status_code})
        except Exception as e:results.append({'source':'OpenAI','status':type(e).__name__})
    print(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
