import json
from .core import load_local_env
from .storage import google_session

load_local_env('../.env.local')
s=google_session()
checks=[('GA Admin','GET','https://analyticsadmin.googleapis.com/v1beta/properties/543866313',None),
        ('GA Data','POST','https://analyticsdata.googleapis.com/v1beta/properties/543866313:runReport',{'dateRanges':[{'startDate':'2026-09-07','endDate':'yesterday'}],'metrics':[{'name':'sessions'}]}),
        ('Drive','GET','https://www.googleapis.com/drive/v3/files/1QKOgh4aFtVM1CQqaqdwlVSklq8s4LiND?fields=id,name',None)]
for name,method,url,body in checks:
    r=s.request(method,url,json=body,timeout=30)
    d=r.json()
    print(json.dumps({'source':name,'status':r.status_code,'error':d.get('error'),'metadata':d.get('metadata'),'rows':d.get('rows')},ensure_ascii=False))
