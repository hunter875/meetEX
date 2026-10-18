import json
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
from app.main import app
out=root/'docs'/'openapi.json'
rendered=json.dumps(app.openapi(),ensure_ascii=False,indent=2)
if '--check' in sys.argv:
    if not out.exists() or out.read_text('utf8')!=rendered:raise SystemExit('OpenAPI changed. Run export_openapi.py then regenerate TypeScript contracts.')
    print('Backend OpenAPI matches saved contract')
else:
    out.write_text(rendered,encoding='utf8');print('Exported docs/openapi.json')
