"""Verify the pre-provisioned private archive before enabling retention."""
import argparse,gzip,json,hashlib
from .core import DATA_ID,load_local_env,stamp
from .storage import google_session,request,Sheets,ApiFailure

def main():
    p=argparse.ArgumentParser();p.add_argument('--env-file');p.add_argument('--file-id',required=True);a=p.parse_args()
    if a.env_file:load_local_env(a.env_file)
    s=google_session(archive=True);base='https://www.googleapis.com/drive/v3/files/'+a.file_id
    meta=request(s,'GET',base,params={'fields':'id,mimeType,capabilities(canEdit),permissions(type,role)'}).json()
    if meta.get('mimeType')!='application/gzip' or not meta.get('capabilities',{}).get('canEdit'):raise ApiFailure('Archive is not writable gzip')
    if not meta.get('permissions') or any(r['type'] in ('anyone','domain') for r in meta['permissions']):raise ApiFailure('Archive privacy not verified')
    data=json.loads(gzip.decompress(request(s,'GET',base,params={'alt':'media'}).content))
    data['verified_at']=stamp();payload=gzip.compress(json.dumps(data,ensure_ascii=False,sort_keys=True).encode())
    request(s,'PATCH','https://www.googleapis.com/upload/drive/v3/files/'+a.file_id,params={'uploadType':'media'},headers={'Content-Type':'application/gzip'},data=payload)
    actual=request(s,'GET',base,params={'alt':'media'}).content
    if hashlib.sha256(actual).digest()!=hashlib.sha256(payload).digest():raise ApiFailure('Archive checksum mismatch')
    store=Sheets(s,DATA_ID,True);store.set('Archive Config',[{'file_id':a.file_id,'status':'write_readback_verified','verified_at':stamp(),'source_link':'https://drive.google.com/file/d/'+a.file_id+'/view','sharing':'private_users_only'}]);store.flush()
    print(json.dumps({'status':'write_readback_verified','file_id':a.file_id,'private':True}))

if __name__=='__main__':main()
