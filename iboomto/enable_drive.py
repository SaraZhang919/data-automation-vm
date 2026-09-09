"""One-time prerequisite setup; never used by the scheduled monitoring job."""
from google.auth.transport.requests import AuthorizedSession
from .core import load_local_env
from .storage import google_session
load_local_env('../.env.local')
base=google_session()
s=AuthorizedSession(base.credentials.with_scopes(['https://www.googleapis.com/auth/cloud-platform']))
r=s.post('https://serviceusage.googleapis.com/v1/projects/182272946347/services/drive.googleapis.com:enable',json={},timeout=30)
data=r.json()
print({'status':r.status_code,'operation':data.get('name'),'message':data.get('error',{}).get('message')})
