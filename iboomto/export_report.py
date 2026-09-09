from pathlib import Path
from .core import load_local_env
from .storage import google_session,request
load_local_env('../.env.local')
s=google_session()
rid='15jBCSt2FqujGjm-L8-PFZTpkMCSDtJVKDl1rEANNNKU'
r=request(s,'GET',f'https://www.googleapis.com/drive/v3/files/{rid}/export',params={'mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
p=Path('outputs/report/live-report.xlsx');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(r.content)
print('Exported the native report for local visual verification')
