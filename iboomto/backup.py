"""Private local rollback snapshot, including formulas and spreadsheet structure."""
import argparse, json, gzip, hashlib
from pathlib import Path
from urllib.parse import quote
from .core import DATA_ID, load_local_env, stamp
from .storage import google_session, request, col

REPORT_ID='15jBCSt2FqujGjm-L8-PFZTpkMCSDtJVKDl1rEANNNKU'

def main():
    p=argparse.ArgumentParser();p.add_argument('--env-file');p.add_argument('--output',required=True);a=p.parse_args()
    if a.env_file:load_local_env(a.env_file)
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True);s=google_session()
    for sid in (DATA_ID,REPORT_ID):
        base='https://sheets.googleapis.com/v4/spreadsheets/'+sid
        meta=request(s,'GET',base).json();snapshot={'id':sid,'at':stamp(),'metadata':meta,'tabs':{}}
        for sheet in meta['sheets']:
            prop=sheet['properties'];gp=prop['gridProperties'];title=prop['title'].replace("'","''")
            rng=f"'{title}'!A1:{col(gp['columnCount'])}{gp['rowCount']}"
            # Bounded grid snapshot preserves values, formulas, formats and hidden dimensions.
            snapshot['tabs'][prop['title']]=request(s,'GET',base,params={'ranges':rng,'includeGridData':'true'}).json()
        payload=json.dumps(snapshot,ensure_ascii=False).encode();dest=out/(sid+'.json.gz')
        dest.write_bytes(gzip.compress(payload))
        assert gzip.decompress(dest.read_bytes())==payload
        dest.with_suffix('.sha256').write_text(hashlib.sha256(payload).hexdigest())
        print(json.dumps({'backup':sid,'tabs':len(snapshot['tabs']),'verified':True}),flush=True)

if __name__=='__main__':main()
