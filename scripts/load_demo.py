import json,sys,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
from app.config import Config
config=Config.load()
def api(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:8765'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+config.token,'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=90) as response:return json.load(response)
corpus=json.loads((root/'fixtures/demo-project.json').read_text('utf8'))
existing=next((p for p in api('/api/v1/projects') if p['name']==corpus['name']),None)
if existing:print('Demo project already exists; use Sources -> Reindex or delete the demo project to reset.');raise SystemExit(0)
project=api('/api/v1/projects',{k:corpus[k] for k in ('name','description','glossary')})
for source in corpus['sources']:
    result=api('/api/v1/projects/'+project['id']+'/sources',{k:v for k,v in source.items() if k!='key'})
    if result['job']['status']!='ready':raise SystemExit('Demo source indexing failed. Inspect the source error in the dashboard.')
print('Created DEMO project with 12 synthetic sources. Choose Demo in Live to try without an API key.')
