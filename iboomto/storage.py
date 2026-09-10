"""Buffered, RAW-value Sheets writes. Only monitor-owned tabs are modified."""
import json
import time
from urllib.parse import quote
from .core import digest, stamp

class ApiFailure(RuntimeError):
    pass

_last_sheet_write=0.0

def request(session, method, url, **kwargs):
    global _last_sheet_write
    timeout=kwargs.pop('timeout',60)
    for attempt in range(4):
        if attempt:
            from .api_usage import METER,category
            with METER.lock:METER.retries[category(method,url,kwargs.get('json'))]+=1
        if method!='GET' and 'sheets.googleapis.com/' in url:
            time.sleep(max(0,1.15-(time.monotonic()-_last_sheet_write)))
            _last_sheet_write=time.monotonic()
        try:
            r = session.request(method, url, timeout=timeout, **kwargs)
        except Exception as exc:
            if attempt == 3: raise ApiFailure(type(exc).__name__) from None
            time.sleep(2**attempt)
            continue
        if r.status_code < 400: return r
        if r.status_code not in (429,500,502,503,504) or attempt == 3:
            # Do not expose authorization headers, server echoes, or query data.
            raise ApiFailure(f"HTTP {r.status_code}")
        time.sleep(min(60, max(30 if r.status_code==429 else 2**attempt, int(r.headers.get('Retry-After','0')) if r.headers.get('Retry-After','0').isdigit() else 0)))
    raise ApiFailure("Request failed")

def google_session(archive=False):
    import os
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    scopes = ["https://www.googleapis.com/auth/analytics.readonly", "https://www.googleapis.com/auth/webmasters.readonly",
              "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.readonly"]
    if archive:scopes[-1]='https://www.googleapis.com/auth/drive'
    raw = os.environ.get("GOOGLE_CREDENTIALS")
    if raw:
        creds = Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
    else:
        path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
        if not path: raise ApiFailure("GOOGLE_CREDENTIALS missing")
        creds = Credentials.from_service_account_file(path, scopes=scopes)
    expected = "gsc-api-service@gsc-api-project-453403.iam.gserviceaccount.com"
    if creds.service_account_email != expected: raise ApiFailure("Unexpected Google service account")
    from .api_usage import METER,category
    class ObservedSession(AuthorizedSession):
        def request(self,method,url,**kwargs):
            key=category(method,url,kwargs.get('json'));METER.pace(key)
            started=time.monotonic();status=0;quota={}
            try:
                result=super().request(method,url,**kwargs);status=result.status_code
                if key[0]=='GA4' and status==200:
                    try:quota=result.json().get('propertyQuota',{})
                    except (ValueError,AttributeError):pass
                return result
            finally:METER.record(key,status,time.monotonic()-started,quota)
    return ObservedSession(creds,refresh_timeout=20)

def col(n):
    out = ""
    while n:
        n, r = divmod(n-1,26); out = chr(65+r)+out
    return out

class Sheets:
    def link(self,name):
        sid=self.tabs.get(name,{}).get('sheetId')
        return 'https://docs.google.com/spreadsheets/d/'+getattr(self,'id','')+'/edit'+('#gid='+str(sid) if sid is not None else '')

    def __init__(self, session, sheet_id, write=False):
        self.s = session; self.id = sheet_id; self.write = write
        self.base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
        self.meta = request(session,"GET",self.base,params={"fields":"sheets.properties"}).json()
        self.tabs = {x['properties']['title']:x['properties'] for x in self.meta.get('sheets',[])}
        self.cache = {}; self.headers = {}; self.dirty = set(); self.old_sizes = {}; self.original = {}

    def read(self, name):
        if name in self.cache: return self.cache[name]
        if name not in self.tabs:
            self.cache[name]=[]; self.headers[name]=[]; self.old_sizes[name]=0
            return []
        props = self.tabs[name]['gridProperties']; width = min(props['columnCount'],60)
        values=[]
        for start in range(1, props['rowCount']+1, 500):
            end=min(start+499,props['rowCount'])
            rng=f"'{name.replace(chr(39),chr(39)*2)}'!A{start}:{col(width)}{end}"
            chunk=request(self.s,"GET",self.base+"/values/"+quote(rng,safe=""),params={"valueRenderOption":"UNFORMATTED_VALUE"}).json().get('values',[])
            values.extend(chunk)
            if len(chunk)<end-start+1: break
        head=values[0] if values else []
        self.headers[name]=head
        from .missing_values import internal
        self.cache[name]=[{k:internal(name,k,v) for k,v in zip(head,row)} for row in values[1:] if any(v != "" for v in row)]
        self.old_sizes[name]=len(values)
        self.original[name]=values
        return self.cache[name]

    def set(self, name, rows, headers=None):
        if name in ('Properties','Page name - manual management','Site Event Logs - Manual') or name in self.tabs and name.lower().endswith('guide'):
            raise ValueError("User configuration/guide is read only during routine runs")
        self.read(name)
        head=list(headers or self.headers[name])
        for row in rows:
            for k in row:
                if k not in head: head.append(k)
        if name in self.tabs and self.headers[name]:
            # Preserve existing column positions; new fields append to the right.
            head=list(self.headers[name])+[k for k in head if k not in self.headers[name]]
        if rows==self.cache[name] and head==self.headers[name]:return
        self.cache[name]=rows; self.headers[name]=head; self.dirty.add(name)

    def upsert(self, name, rows, keys=("id",), replace_where=None):
        old=self.read(name)
        if replace_where: old=[r for r in old if not replace_where(r)]
        def key(r): return tuple(str(r.get(k,"")) for k in keys)
        indexed={key(r):r for r in old}
        for row in rows: indexed[key(row)]=row
        self.set(name,list(indexed.values()))

    def flush(self):
        if not self.write: return
        names=[n for n in sorted(self.dirty) if self.headers[n]]
        if not names:return
        edits=[]
        for name in names:
            rows=self.cache[name]; head=self.headers[name]
            needed=max(100,len(rows)+1,self.old_sizes.get(name,0))
            if name not in self.tabs:
                edits.append({"addSheet":{"properties":{"title":name,"gridProperties":{"rowCount":needed,"columnCount":max(26,len(head)),"frozenRowCount":1}}}})
            else:
                p=self.tabs[name]
                edits.append({"updateSheetProperties":{"properties":{"sheetId":p['sheetId'],"gridProperties":{"rowCount":max(needed,p['gridProperties']['rowCount']),"columnCount":max(len(head),p['gridProperties']['columnCount'])}},"fields":"gridProperties.rowCount,gridProperties.columnCount"}})
        result=request(self.s,'POST',self.base+':batchUpdate',json={'requests':edits}).json()
        for reply in result.get('replies',[]):
            if 'addSheet' in reply:
                prop=reply['addSheet']['properties'];self.tabs[prop['title']]=prop
        writes=[];formats=[]
        def cell(v):
            if isinstance(v,list) and all(isinstance(x,str) for x in v):v='\n\n'.join(v)
            elif isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False,separators=(',',':'))
            if isinstance(v,str) and len(v)>49000:raise ApiFailure('Cell exceeds Sheets limit; split evidence before writing')
            return '' if v is None else v
        for name in names:
            rows=self.cache[name];head=self.headers[name]
            from .layout import ordered_headers
            prior=getattr(self,'original',{}).get(name,[])
            if not prior:head=ordered_headers(name,head)
            self.headers[name]=head
            width=max(len(head),len(prior[0]) if prior else 0)
            if name.endswith('Guide'):
                # Legacy guide rows can have trailing content beyond their short header.
                width=max(width,max((len(row) for row in prior),default=0))
            from .missing_values import display
            matrix=[head+['']*(width-len(head))]+[[cell(display(name,k,row.get(k,""))) for k in head]+['']*(width-len(head)) for row in rows]
            if self.old_sizes.get(name,0)>len(matrix):
                matrix += [[""]*width for _ in range(self.old_sizes[name]-len(matrix))]
            def normalized(row):return row+['']*(width-len(row))
            # Write only changed contiguous rows, preserving unaffected cells and formatting.
            start=0
            while start<len(matrix):
                if start<len(prior) and normalized(prior[start])==matrix[start]:start+=1;continue
                end=start+1
                while end<len(matrix) and end-start<500 and (end>=len(prior) or normalized(prior[end])!=matrix[end]):end+=1
                writes.append({'range':f"'{name}'!A{start+1}",'values':matrix[start:end]});start=end
            sid=self.tabs[name]['sheetId']
            if prior:
                # Existing sheets are values-only: widths, hidden flags, freeze panes,
                # number formats, notes and guide annotations belong to the user.
                if len(rows)+1>len(prior) and len(prior)>1:
                    formats.append({'copyPaste':{'source':{'sheetId':sid,'startRowIndex':len(prior)-1,'endRowIndex':len(prior),'startColumnIndex':0,'endColumnIndex':len(prior[0])},
                        'destination':{'sheetId':sid,'startRowIndex':len(prior),'endRowIndex':len(rows)+1,'startColumnIndex':0,'endColumnIndex':len(prior[0])},'pasteType':'PASTE_FORMAT'}})
                continue
            formats.extend([
                {"repeatCell":{"range":{"sheetId":sid,"startRowIndex":0,"endRowIndex":1},"cell":{"userEnteredFormat":{"backgroundColor":{"red":.10,"green":.20,"blue":.30},"textFormat":{"bold":True,"foregroundColor":{"red":1,"green":1,"blue":1}},"wrapStrategy":"WRAP"}},"fields":"userEnteredFormat"}},
                {"updateSheetProperties":{"properties":{"sheetId":sid,"gridProperties":{"frozenRowCount":1}},"fields":"gridProperties.frozenRowCount"}}
            ])
            if name=='AI Cache':
                formats.append({'updateSheetProperties':{'properties':{'sheetId':sid,'hidden':True},'fields':'hidden'}})
            # Keep working tables readable; bounded row formatting never touches Properties.
            formatting=[]
            from .layout import format_columns
            formatting.extend(format_columns(sid,name,head,len(rows),not prior or prior[0]!=head))
            if name in ('Overview','Weekly Overview','Monthly Overview'):
                formatting += [{'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'COLUMNS','startIndex':2,'endIndex':3},'properties':{'pixelSize':760},'fields':'pixelSize'}},
                               {'repeatCell':{'range':{'sheetId':sid,'startRowIndex':1,'endRowIndex':len(rows)+1,'startColumnIndex':2,'endColumnIndex':3},'cell':{'userEnteredFormat':{'wrapStrategy':'WRAP'}},'fields':'userEnteredFormat.wrapStrategy'}},
                               {'autoResizeDimensions':{'dimensions':{'sheetId':sid,'dimension':'ROWS','startIndex':1,'endIndex':len(rows)+1}}}]
            if name in ('Issues','Report History','Deep Analysis','AI Usage','Data Status') and not prior:
                for index,key in enumerate(head):
                    width=600 if key in ('summary','findings','actions','limitations','evidence') else 480 if key=='url' else 230 if key.endswith('_at') or key in ('at','first_seen','last_seen','source') else 165
                    formatting.append({'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'COLUMNS','startIndex':index,'endIndex':index+1},'properties':{'pixelSize':width},'fields':'pixelSize'}})
                    if key in ('summary','findings','actions','limitations','evidence','url') and rows:
                        formatting.append({'repeatCell':{'range':{'sheetId':sid,'startRowIndex':1,'endRowIndex':len(rows)+1,'startColumnIndex':index,'endColumnIndex':index+1},'cell':{'userEnteredFormat':{'wrapStrategy':'WRAP'}},'fields':'userEnteredFormat.wrapStrategy'}})
                if rows:formatting.append({'autoResizeDimensions':{'dimensions':{'sheetId':sid,'dimension':'ROWS','startIndex':1,'endIndex':len(rows)+1}}})
            formats.extend(formatting)
            if name in getattr(self,'guide_links',{}):
                from .guide import guide_format_requests
                formats.extend(guide_format_requests(sid,rows,self.guide_links[name],width))
        batch=[];size=0
        for write in writes:
            n=len(json.dumps(write,ensure_ascii=False).encode())
            if batch and size+n>1500000:
                request(self.s,'POST',self.base+'/values:batchUpdate',json={'valueInputOption':'RAW','data':batch});batch=[];size=0
            batch.append(write);size+=n
        if batch:request(self.s,'POST',self.base+'/values:batchUpdate',json={'valueInputOption':'RAW','data':batch})
        if formats:request(self.s,'POST',self.base+':batchUpdate',json={'requests':formats})
        for name in names:
            rows=self.cache[name]
            self.old_sizes[name]=len(rows)+1
            if not hasattr(self,'original'):self.original={}
            self.original[name]=[self.headers[name]]+[[cell(display(name,k,r.get(k,''))) for k in self.headers[name]] for r in rows]
        self.dirty.clear()
