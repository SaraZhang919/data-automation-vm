"""Preserve a verified local backup before compacting the old Clarity tab."""
import argparse,json,hashlib
from pathlib import Path
from .core import DATA_ID,load_local_env
from .storage import Sheets,google_session,request
from .clarity_summary import from_legacy

def main():
    p=argparse.ArgumentParser();p.add_argument('--env-file');p.add_argument('--backup',required=True);a=p.parse_args()
    if a.env_file:load_local_env(a.env_file)
    store=Sheets(google_session(),DATA_ID,True)
    if 'Clarity Daily' not in store.tabs:
        print(json.dumps({'status':'already_migrated'}));return
    if 'Clarity Snapshots' in store.tabs:raise ValueError('Both Clarity tables exist; reconcile before migration')
    raw=store.read('Clarity Daily');serialized=json.dumps(raw,ensure_ascii=False).encode()
    dest=Path(a.backup);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(serialized)
    if hashlib.sha256(dest.read_bytes()).digest()!=hashlib.sha256(serialized).digest():raise ValueError('Backup mismatch')
    rows=from_legacy(raw)
    if raw and not rows:raise ValueError('No overall snapshot could be recovered; old rows retained')
    sid=store.tabs['Clarity Daily']['sheetId']
    request(store.s,'POST',store.base+':batchUpdate',json={'requests':[{'updateSheetProperties':{'properties':{'sheetId':sid,'title':'Clarity Snapshots'},'fields':'title'}}]})
    store=Sheets(store.s,DATA_ID,True)
    store.set('Clarity Snapshots',rows,headers=list(rows[0]) if rows else ['day','window_start','window_end','total_sessions'])
    store.flush()
    verified=Sheets(store.s,DATA_ID).read('Clarity Snapshots')
    if len(verified)!=len(rows):raise ValueError('Clarity snapshot readback failed')
    print(json.dumps({'status':'verified','old_rows':len(raw),'snapshot_rows':len(rows),'retained_window_types':[r['window_type'] for r in rows]}))

if __name__=='__main__':main()
