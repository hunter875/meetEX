from pathlib import Path
import json,re,xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1];docs=root/'docs'
if (docs/'PHASE5_REPORT.md').exists():
    import runpy,sys
    runpy.run_path(str(root/'scripts/check_phase5_docs.py'),run_name='__main__')
    raise SystemExit(0)
phase1=(docs/'evidence/phase1/semantic-review.json').exists()
phase2=(docs/'evidence/phase2/review.json').exists()
phase3=(docs/'evidence/phase3/review.json').exists()
phase4=(docs/'evidence/phase4/review.json').exists()
current_phase='phase4' if phase4 else 'phase3' if phase3 else 'phase2' if phase2 else 'phase1' if phase1 else None
qa_path=docs/(f'evidence/{current_phase}/documentation-qa.json' if current_phase else 'evidence/documentation-qa.json')
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
        # This audit writes its own evidence only after the checks pass.
        if not resolved.exists() and resolved!=qa_path:bad.append(f'{path.name}: {target}')
assert not bad,bad
for line in report.splitlines():
    if line.startswith('| ') and ' | PASS | ' in line:
        files=line.split('|')[4].strip().split('; ')
        assert all((docs/'evidence'/file).exists() for file in files if file.split('/')[-1]!='documentation-qa.json'),line
tree=ET.parse(docs/(f'evidence/{current_phase}/backend-final.xml' if current_phase else 'evidence/backend-tests.xml')).getroot()
assert all(int(s.get('failures','0'))==0 and int(s.get('errors','0'))==0 for s in tree.iter('testsuite'))
front=json.loads((docs/(f'evidence/{current_phase}/frontend-final.json' if current_phase else 'evidence/extension-tests.json')).read_text('utf8'));assert front['numFailedTests']==0 and front['numPassedTests']>0
browser=json.loads((docs/(f'evidence/{current_phase}/browser-final-results.json' if current_phase else 'evidence/e2e-results.json')).read_text('utf8'));assert browser['stats']['unexpected']==0 and browser['stats']['expected']==(6 if phase4 else 5 if phase3 else 4 if phase2 else 3)
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
    phase=json.loads((docs/('evidence/phase4/semantic-regression.json' if phase4 else 'evidence/phase3/semantic-regression.json' if phase3 else 'evidence/phase2/semantic-regression.json' if phase2 else 'evidence/phase1/semantic-review.json')).read_text('utf8'))
    assert phase['result']=='PASS' and all(p['blocked'] for p in phase['original_probes'])
    assert all(g['false_accepts']==g['false_rejects']==0 for g in phase['groups'].values())
    for path,expected in phase['source_hashes'].items():
        assert hashlib.sha256((root/path).read_text('utf8').encode('utf8')).hexdigest()==expected,path
    record['phase1']='PASS within declared grammar/alias scope; not general entailment'
    record['latency_target']='Historical pre-phase1 benchmark; current provider latency NOT TESTED'
if phase2:
    latest=json.loads((docs/'evidence/phase2/review.json').read_text('utf8'))
    assert latest['live_gate']=='NOT TESTED' and latest['provider_paid_calls']==0
    for path,expected in latest['source_hashes'].items():
        if phase3 and not ((path=='backend/app/storage.py' and not phase4) or path.startswith(('extension/src/content/','extension/src/background/'))):continue
        assert hashlib.sha256((root/path).read_text('utf8').encode('utf8')).hexdigest()==expected,path
    record['phase2']='Automated capture/recovery/clock checks PASS; live NOT TESTED'
if phase3:
    latest=json.loads((docs/'evidence/phase3/review.json').read_text('utf8'))
    assert latest['result'].startswith('PARTIAL') and latest['paid_provider_calls']==0
    assert latest['after']['missed']==latest['after']['false_trigger']==0
    assert not latest['objectives']['logical_requests_reduction_fraction_min']['passed']
    assert not latest['objectives']['short_question_schedule_wait_max_ms']['passed']
    for path,expected in latest['source_hashes'].items():
        if phase4 and path in json.loads((docs/'evidence/phase4/review.json').read_text('utf8'))['source_hashes']:continue
        assert hashlib.sha256((root/path).read_text('utf8').encode('utf8')).hexdigest()==expected,path
    assert 'PARTIAL' in report and 'PHASE3_REPORT.md' in report
    record['phase3']=latest['result']
    record['live_gates']['phase3_provider']='NOT TESTED'
if phase4:
    latest=json.loads((docs/'evidence/phase4/review.json').read_text('utf8'))
    assert latest['result'].startswith('PARTIAL') and latest['provider_paid_calls']==0
    assert latest['item_quality']['correct_items']==latest['item_quality']['expected_items']==38
    assert latest['relation_quality']['wrong']==latest['relation_quality']['extra']==0
    for path,expected in latest['source_hashes'].items():assert hashlib.sha256((root/path).read_text('utf8').encode('utf8')).hexdigest()==expected,path
    assert 'PHASE4_REPORT.md' in report
    record['phase4']=latest['result'];record['live_gates']['phase4_model']='NOT TESTED'
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--output')
args=parser.parse_args()
output=root/args.output if args.output else qa_path
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(record,indent=2),encoding='utf8')
print(json.dumps(record))
