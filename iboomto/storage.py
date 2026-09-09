"""Buffered, RAW-value Sheets writes. Only monitor-owned tabs are modified."""
import json
import time
from urllib.parse import quote
from .core import digest, stamp

class ApiFailure(RuntimeError):
    pass

def request(session, method, url, **kwargs):
    for attempt in range(4):
        try:
            r = session.request(method, url, timeout=kwargs.pop("timeout", 60), **kwargs)
        except Exception as exc:
            if attempt == 3: raise ApiFailure(type(exc).__name__) from None
            time.sleep(2**attempt)
            continue
        if r.status_code < 400: return r
        if r.status_code not in (429,500,502,503,504) or attempt == 3:
            # Do not expose authorization headers, server echoes, or query data.
            raise ApiFailure(f"HTTP {r.status_code}")
        time.sleep(min(30, max(2**attempt, int(r.headers.get('Retry-After','0')) if r.headers.get('Retry-After','0').isdigit() else 0)))
    raise ApiFailure("Request failed")

def google_session():
    import os
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    scopes = ["https://www.googleapis.com/auth/analytics.readonly", "https://www.googleapis.com/auth/webmasters.readonly",
              "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.readonly"]
    raw = os.environ.get("GOOGLE_CREDENTIALS")
    if raw:
        creds = Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
    else:
        path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
        if not path: raise ApiFailure("GOOGLE_CREDENTIALS missing")
        creds = Credentials.from_service_account_file(path, scopes=scopes)
    expected = "gsc-api-service@gsc-api-project-453403.iam.gserviceaccount.com"
    if creds.service_account_email != expected: raise ApiFailure("Unexpected Google service account")
    return AuthorizedSession(creds)

def col(n):
    out = ""
    while n:
        n, r = divmod(n-1,26); out = chr(65+r)+out
    return out

class Sheets:
    def __init__(self, session, sheet_id, write=False):
        self.s = session; self.id = sheet_id; self.write = write
        self.base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
        self.meta = request(session,"GET",self.base,params={"fields":"sheets.properties"}).json()
        self.tabs = {x['properties']['title']:x['properties'] for x in self.meta.get('sheets',[])}
        self.cache = {}; self.headers = {}; self.dirty = set(); self.old_sizes = {}

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
        self.cache[name]=[dict(zip(head,row)) for row in values[1:] if any(v != "" for v in row)]
        self.old_sizes[name]=len(values)
        return self.cache[name]

    def set(self, name, rows, headers=None):
        if name == 'Properties': raise ValueError("Properties is read only")
        self.read(name)
        self.cache[name]=rows
        head=list(headers or self.headers[name])
        for row in rows:
            for k in row:
                if k not in head: head.append(k)
        self.headers[name]=head; self.dirty.add(name)

    def upsert(self, name, rows, keys=("id",), replace_where=None):
        old=self.read(name)
        if replace_where: old=[r for r in old if not replace_where(r)]
        def key(r): return tuple(str(r.get(k,"")) for k in keys)
        indexed={key(r):r for r in old}
        for row in rows: indexed[key(row)]=row
        self.set(name,list(indexed.values()))

    def flush(self):
        if not self.write: return
        for name in sorted(self.dirty):
            rows=self.cache[name]; head=self.headers[name]
            if not head: continue
            needed=max(100,len(rows)+1,self.old_sizes.get(name,0))
            requests=[]
            if name not in self.tabs:
                requests.append({"addSheet":{"properties":{"title":name,"gridProperties":{"rowCount":needed,"columnCount":max(26,len(head)),"frozenRowCount":1}}}})
            else:
                p=self.tabs[name]
                requests.append({"updateSheetProperties":{"properties":{"sheetId":p['sheetId'],"gridProperties":{"rowCount":max(needed,p['gridProperties']['rowCount']),"columnCount":max(len(head),p['gridProperties']['columnCount'])}},"fields":"gridProperties.rowCount,gridProperties.columnCount"}})
            result=request(self.s,"POST",self.base+":batchUpdate",json={"requests":requests}).json()
            if name not in self.tabs: self.tabs[name]=result['replies'][0]['addSheet']['properties']
            def cell(v):
                if isinstance(v,(dict,list)): return json.dumps(v,ensure_ascii=False,separators=(',',':'))
                return "" if v is None else v
            matrix=[head]+[[cell(row.get(k,"")) for k in head] for row in rows]
            if self.old_sizes.get(name,0)>len(matrix):
                matrix += [[""]*len(head) for _ in range(self.old_sizes[name]-len(matrix))]
            for start in range(0,len(matrix),500):
                rng=quote(f"'{name}'!A{start+1}",safe="")
                request(self.s,"PUT",self.base+"/values/"+rng,params={"valueInputOption":"RAW"},json={"values":matrix[start:start+500]})
            sid=self.tabs[name]['sheetId']
            request(self.s,"POST",self.base+":batchUpdate",json={"requests":[
                {"repeatCell":{"range":{"sheetId":sid,"startRowIndex":0,"endRowIndex":1},"cell":{"userEnteredFormat":{"backgroundColor":{"red":.10,"green":.20,"blue":.30},"textFormat":{"bold":True,"foregroundColor":{"red":1,"green":1,"blue":1}},"wrapStrategy":"WRAP"}},"fields":"userEnteredFormat"}},
                {"updateSheetProperties":{"properties":{"sheetId":sid,"gridProperties":{"frozenRowCount":1}},"fields":"gridProperties.frozenRowCount"}}
            ]})
            self.old_sizes[name]=len(rows)+1
        self.dirty.clear()
