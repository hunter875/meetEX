from pathlib import Path
import json,re,xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1];docs=root/'docs'
phase1=(docs/'evidence/phase1/semantic-review.json').exists()
req=set(re.findall(r'^\| (REQ-\d+)',(docs/'spec/REQUIREMENTS.md').read_text('utf8'),re.M))
tasks=set(re.findall(r'^\| (T-\d+)',(docs/'spec/IMPLEMENTATION_PLAN.md').read_text('utf8'),re.M))
checks=set(re.findall(r'^\| ([A-Z]+-\d+)',(docs/'spec/ACCEPTANCE_SPEC.md').read_text('utf8'),re.M))
trace=(docs/'TRACEABILITY.md').read_text('utf8');report=(docs/'ACCEPTANCE_REPORT.md').read_text('utf8');status=(docs/'IMPLEMENTATION_STATUS.md').read_text('utf8')
assert (len(req),len(tasks),len(checks))==(30,28,46)
assert req.issubset(set(re.findall(r'REQ-\d+',trace))) and tasks.issubset(set(re.findall(r'T-\d+',trace)))
assert checks.issubset(set(re.findall(r'\b[A-Z]+-\d+\b',trace))) and checks.issubset(set(re.findall(r'^\| ([A-Z]+-\d+)',report,re.M)))
assert tasks.issubset(set(re.findall(r'T-\d+',status)))
assert 'NOT TESTED' in report and 'Không phải MVP VERIFIED' in report
bad=[]
for path in [root/'README.md',*docs.glob('*.md'),*docs.glob('spec/*.md')]:
    for target in re.findall(r'\]\(([^)]+)\)',path.read_text('utf8')):
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target) or target.startswith('#'):continue
        resolved=(path.parent/target.split('#')[0]).resolve()
        if not resolved.exists():bad.append(f'{path.name}: {target}')
assert not bad,bad
for line in report.splitlines():
    if line.startswith('| ') and ' | PASS | ' in line:
        files=line.split('|')[4].strip().split('; ')
        assert all((docs/'evidence'/file).exists() for file in files if file.split('/')[-1]!='documentation-qa.json'),line
tree=ET.parse(docs/('evidence/phase1/backend-final.xml' if phase1 else 'evidence/backend-tests.xml')).getroot()
assert all(int(s.get('failures','0'))==0 and int(s.get('errors','0'))==0 for s in tree.iter('testsuite'))
front=json.loads((docs/('evidence/phase1/frontend-final.json' if phase1 else 'evidence/extension-tests.json')).read_text('utf8'));assert front['numFailedTests']==0 and front['numPassedTests']>0
browser=json.loads((docs/('evidence/phase1/browser-final-results.json' if phase1 else 'evidence/e2e-results.json')).read_text('utf8'));assert browser['stats']['unexpected']==0 and browser['stats']['expected']==3
live_review=docs/'evidence/live-provider-review.json'
if live_review.exists():
    live=json.loads(live_review.read_text('utf8'))
    assert len(live['cases'])==6 and all(c['status']=='PASS' for c in live['cases']) and live['credential_cleared']
    assert all((docs/'evidence'/c['evidence_file']).exists() for c in live['cases'])
extended_review=docs/'evidence/extended-live-review.json'
if extended_review.exists():
    extended=json.loads(extended_review.read_text('utf8'))
    assert len(extended['cases'])==10 and extended['result']=='PASS' and extended['credential_cleared']
    assert all((docs/'evidence'/c['evidence_file']).exists() for c in extended['cases'])
record=dict(requirements=len(req),tasks=len(tasks),checks=len(checks),local_links_valid=True,claimed_pass_evidence_exists=True,backend_failures=0,frontend_failures=0,e2e_passed=browser['stats']['expected'],live_gates={'Meet':'NOT TESTED','provider_synthetic':'6 reviewed samples' if live_review.exists() else 'NOT TESTED'},result='PASS')
if extended_review.exists():record['live_gates']['provider_synthetic']='6 initial + 10 extended reviewed samples'
speed_review=docs/'evidence/speed-review.json'
if speed_review.exists():
    speed=json.loads(speed_review.read_text('utf8'))
    assert speed['result']=='PASS' and len(speed['cases'])==16 and speed['credential_cleared']
    record['latency_target']='~1.5 s median on matched synthetic corpus; not a per-request SLA'

routing_review=docs/'evidence/routing-review.json'
if routing_review.exists():
    import hashlib
    routing=json.loads(routing_review.read_text('utf8'))
    assert routing['passed']==routing['total']==len(json.loads((root/'fixtures/routing-scenarios.json').read_text('utf8')))
    assert routing['hash_format']=='utf8-lf'
    assert routing['classifier_sha256']==hashlib.sha256((root/'backend/app/routing.py').read_text('utf8').encode('utf8')).hexdigest()
    assert routing['fixture_sha256']==hashlib.sha256((root/'fixtures/routing-scenarios.json').read_text('utf8').encode('utf8')).hexdigest()
    record['routing']='Local synthetic fixtures pass; not real-meeting accuracy or new provider latency'

if phase1:
    import hashlib
    phase=json.loads((docs/'evidence/phase1/semantic-review.json').read_text('utf8'))
    assert phase['result']=='PASS' and all(p['blocked'] for p in phase['original_probes'])
    assert all(g['false_accepts']==g['false_rejects']==0 for g in phase['groups'].values())
    for path,expected in phase['source_hashes'].items():
        assert hashlib.sha256((root/path).read_text('utf8').encode('utf8')).hexdigest()==expected,path
    record['phase1']='PASS within declared grammar/alias scope; not general entailment'
    record['latency_target']='Historical pre-phase1 benchmark; current provider latency NOT TESTED'
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--output')
args=parser.parse_args()
output=root/args.output if args.output else docs/('evidence/phase1/documentation-qa.json' if phase1 else 'evidence/documentation-qa.json')
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(record,indent=2),encoding='utf8')
print(json.dumps(record))
