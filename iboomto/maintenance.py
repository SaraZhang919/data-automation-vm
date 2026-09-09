"""Retention is fail-closed: archive round-trip verification precedes removal."""
import gzip,json,hashlib,os
from datetime import date,timedelta
from .core import stamp,digest
from .storage import request,ApiFailure

def expired(row,tab,today):
    period=row.get('period','daily');raw=row.get('end') or row.get('revised_at') or row.get('observed_at') or row.get('checked_at') or row.get('finished_at') or ''
    try:d=date.fromisoformat(str(raw)[:10])
    except ValueError:return False
    if period=='monthly':
        months=(today.year-d.year)*12+today.month-d.month;return months>36
    keep=728 if period=='weekly' else 365 if tab in ('GA4 Site','GSC Site') else 90
    return d<today-timedelta(days=keep)

def maintain(store,today):
    eligible=['GA4 Site','GSC Site','GA4 Channels','GA4 Landing Pages','GA4 Events','GA4 Business Events','GSC Pages','GSC Queries',
              'Sitemap History','Technical History','Data Revisions','Run Status','Clarity Daily','Clarity Requests']
    old={tab:[r for r in store.read(tab) if expired(r,tab,today)] for tab in eligible}
    old={tab:rows for tab,rows in old.items() if rows};count=sum(map(len,old.values()))
    cfg=next(iter(store.read('Archive Config')),{});file_id=cfg.get('file_id') or os.environ.get('IBOOMTO_ARCHIVE_FILE_ID')
    status={'id':str(today),'at':stamp(),'expired_rows':count,'archive_file_id':file_id or '',
            'status':'not_due' if not count else 'archive_not_configured','allocated_cells':sum(p.get('gridProperties',{}).get('rowCount',0)*p.get('gridProperties',{}).get('columnCount',0) for p in store.tabs.values())}
    if not count:
        store.upsert('Storage Status',[status]);return status
    if not file_id:
        store.upsert('Storage Status',[status]);return status
    # Archive file must be pre-provisioned by its human owner; service accounts cannot own My Drive storage.
    from .storage import google_session
    s=google_session(archive=True)
    base='https://www.googleapis.com/drive/v3/files/'+file_id
    meta=request(s,'GET',base,params={'fields':'id,mimeType,capabilities(canEdit),permissions(type,role)'}).json()
    if meta.get('mimeType')!='application/gzip' or not meta.get('capabilities',{}).get('canEdit'):raise ApiFailure('Archive must be an editable gzip file')
    if any(p.get('type') in ('anyone','domain') for p in meta.get('permissions',[])):raise ApiFailure('Archive sharing is not private')
    raw=request(s,'GET',base,params={'alt':'media'}).content
    archive=json.loads(gzip.decompress(raw));tables=archive.setdefault('tables',{})
    for tab,rows in old.items():
        existing={r.get('id',digest(r)):r for r in tables.get(tab,[])}
        for r in rows:existing[r.get('id',digest(r))]=r
        tables[tab]=list(existing.values())
    archive['updated_at']=stamp();payload=gzip.compress(json.dumps(archive,ensure_ascii=False,sort_keys=True).encode())
    request(s,'PATCH','https://www.googleapis.com/upload/drive/v3/files/'+file_id,params={'uploadType':'media'},headers={'Content-Type':'application/gzip'},data=payload)
    downloaded=request(s,'GET',base,params={'alt':'media'}).content
    if hashlib.sha256(downloaded).digest()!=hashlib.sha256(payload).digest():raise ApiFailure('Archive readback checksum mismatch; source rows retained')
    for tab,rows in old.items():
        ids={r.get('id',digest(r)) for r in rows};store.set(tab,[r for r in store.read(tab) if r.get('id',digest(r)) not in ids])
    status.update(status='archived_verified',sha256=hashlib.sha256(payload).hexdigest(),source_link='https://drive.google.com/file/d/'+file_id+'/view')
    store.upsert('Storage Status',[status]);return status
