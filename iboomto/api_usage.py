"""Process-wide, credential-free Google API counters and minute pacing."""
import re
import time
import threading
from collections import defaultdict, deque
from urllib.parse import urlsplit
from .core import digest, stamp


def category(method,url,body=None):
    host=urlsplit(url).hostname or '';path=urlsplit(url).path;body=body or {}
    if host=='sheets.googleapis.com':return 'Sheets', 'read' if method.upper()=='GET' else 'write',''
    if host=='analyticsdata.googleapis.com':
        match=re.search(r'/properties/(\d+)',path)
        return 'GA4','runReport',match.group(1) if match else ''
    if 'urlInspection' in path:return 'GSC','inspection','iboomto.com'
    if 'searchAnalytics' in path:
        dims=body.get('dimensions',[])
        return 'GSC','queries' if 'query' in dims else 'pages' if 'page' in dims else 'aggregate','iboomto.com'
    if '/webmasters/' in path:return 'GSC','sites','iboomto.com'
    if '/drive/' in path:return 'Drive',method.upper(),''
    return 'Google other',method.upper(),''


class Meter:
    def __init__(self):
        self.lock=threading.Lock();self.reset()

    def reset(self,run_id=''):
        self.run_id=run_id or digest(stamp());self.counts={};self.last={};self.events=defaultdict(deque);self.retries=defaultdict(int)

    def pace(self,key):
        api,op,_=key
        group=(api,op if api=='Sheets' else '')
        interval=1.3 if api=='Sheets' else .15 if api=='GSC' else 0
        if not interval:return
        with self.lock:
            delay=max(0,interval-(time.monotonic()-self.last.get(group,0)))
            if delay:time.sleep(delay)
            self.last[group]=time.monotonic()

    def record(self,key,status,elapsed,quota=None):
        with self.lock:
            r=self.counts.setdefault(key,{'requests':0,'http_429':0,'http_403':0,'server_errors':0,'transport_errors':0,'elapsed_seconds':0,'peak_requests_60s':0,'quota':{}})
            r['requests']+=1;r['http_429']+=status==429;r['http_403']+=status==403
            r['server_errors']+=status>=500;r['transport_errors']+=status==0;r['elapsed_seconds']+=elapsed
            times=self.events[key];now=time.monotonic();times.append(now)
            while times and times[0]<=now-60:times.popleft()
            r['peak_requests_60s']=max(r['peak_requests_60s'],len(times))
            for name,q in (quota or {}).items():
                if not isinstance(q,dict):continue
                old=r['quota'].setdefault(name,{'consumed_in_observed_responses':0})
                old['consumed_in_observed_responses']+=q.get('consumed',0)
                if 'remaining' in q:
                    old['latest_remaining']=q['remaining'];old['min_remaining']=min(old.get('min_remaining',q['remaining']),q['remaining'])

    def rows(self):
        result=[]
        for (api,op,entity),data in list(self.counts.items()):
            q=data['quota'];low=any(q.get(k,{}).get('min_remaining',limit)<limit*.1 for k,limit in [('tokensPerDay',200000),('tokensPerHour',40000),('tokensPerProjectPerHour',14000)])
            result.append({'id':digest([self.run_id,api,op,entity]),'run_id':self.run_id,'at':stamp(),'api':api,'operation':op,'property_or_site':entity,
                           **data,'retry_attempts':self.retries[(api,op,entity)],'status':'rate_limited' if data['http_429'] else 'review_errors' if data['http_403'] or data['server_errors'] or data['transport_errors'] else 'low_quota' if low else 'observed_ok',
                           'coverage':'This process only; includes application retries; excludes authentication and final telemetry flush. GSC load quota remaining is not exposed.'})
        return result


METER=Meter()
