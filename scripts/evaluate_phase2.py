"""Review offline Phase 2 evidence, separating synthetic and live gates."""
import hashlib
import json
import math
import platform
import statistics
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidence/phase2'


def read(name):return json.loads((EVIDENCE/name).read_text('utf-8'))
def summary(values):
    values=sorted(values)
    return dict(n=len(values),median_ms=statistics.median(values) if values else None,p95_ms=values[math.ceil(.95*len(values))-1] if values else None,max_ms=max(values) if values else None)


def main():
    backend=ET.parse(EVIDENCE/'backend-final.xml').getroot()
    assert all(int(s.get('failures',0))==int(s.get('errors',0))==0 for s in backend.iter('testsuite'))
    front=read('frontend-final.json');assert front['numFailedTests']==0
    browser=read('browser-final-results.json');assert browser['stats']['unexpected']==0 and browser['stats']['expected']==4
    semantic=read('semantic-regression.json');assert semantic['result']=='PASS' and all(p['blocked'] for p in semantic['original_probes'])
    before=read('replay-before.json')
    before_errors=[t['title'] for suite in before['testResults'] for t in suite['assertionResults'] if t['status']=='failed' and t['title'].startswith('synthetic replay:')]
    assert len(before_errors)==8
    capture=read('browser-final/phase2-recovery.json');assert not capture['live_meet_tested']
    assert [f['outage_ms'] for f in capture['faults']]==[5000,20000] and all(f['transcript_recovered'] and f['unacked']==0 for f in capture['faults'])
    snapshot=capture['snapshot'];ids={r['id'] for r in snapshot['requests']}
    backend_records=[r for r in capture['backend_latency'] if r['request_id'] in ids]
    telemetry=[r for r in capture['telemetry']['latencyRecords'] if r.get('meeting_id')==snapshot['id']]
    assert telemetry,'Scoped content telemetry missing; rebuild extension before E2E'
    assert {'ready','stale','error','cancelled'}.issubset({r['outcome'] for r in backend_records})
    rendered={r['request_id'] for r in telemetry if r['stage']=='card_rendered_notification'}
    groups=defaultdict(list)
    for r in backend_records:groups['/'.join(r[k] for k in ('trigger','temperature','retrieval','provider_mode','outcome'))].append(r)
    grouped={key:dict(request_n=len(rows),provider=summary([r['provider_ms'] for r in rows if any(m['stage']=='provider_started' for m in r['marks'])]),validation=summary([r['validation_ms'] for r in rows if any(m['stage']=='validation_completed' for m in r['marks'])]),stable_to_scheduled=summary([r['stable_to_scheduled_ms'] for r in rows if r.get('stable_to_scheduled_ms') is not None]),missing_render_n=sum(r['request_id'] not in rendered for r in rows)) for key,rows in groups.items()}
    measures={field:summary([r[field] for r in telemetry if field in r]) for field in ('observed_to_ack_ms','stable_to_schedule_received_ms','observed_to_rendered_notification_ms','stable_to_rendered_notification_ms')}
    render_groups=defaultdict(list)
    for r in telemetry:
        if r['stage']=='card_rendered_notification':render_groups[r['trigger']+'/'+r['outcome']].append(r)
    render_grouped={key:{field:summary([r[field] for r in rows if field in r]) for field in ('observed_to_rendered_notification_ms','stable_to_rendered_notification_ms')} for key,rows in render_groups.items()}
    candidates=subprocess.check_output(['git','diff','--name-only','c81a95b1c24726a1b1ebaa309bdd5d6890cb3833'],cwd=ROOT,text=True).splitlines()
    candidates+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    paths=sorted(set(p for p in candidates if (p.startswith(('backend/','extension/','e2e/','fixtures/phase2/','scripts/')) or p=='playwright.config.ts') and Path(p).suffix in ('.py','.ts','.tsx','.js','.json')))
    record=dict(result='PASS automated scope; live validation pending',client_date='2026-10-18',timezone='America/Los_Angeles',branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),base_commit='c81a95b1c24726a1b1ebaa309bdd5d6890cb3833',initial_worktree='clean',platform=platform.platform(),python=platform.python_version(),baseline=dict(backend=219,frontend=13),final=dict(backend=sum(int(s.get('tests',0)) for s in backend.iter('testsuite')),frontend=front['numPassedTests'],browser=4),before_product_failures=before_errors,before_harness_note='The first positive control mistakenly selected a passing negation case. Corrected to the unchanged failing numeric case; original raw failure is retained.',replay_provenance='18 synthetic snapshots, production reducer + 8 DOM tests; not captured/live Meet data',faults=capture['faults'],backend_latency_groups=grouped,extension_latency=measures,render_groups=render_grouped,latency_note='MockTransport SSE only. Extension one content-process monotonic clock includes message delivery. Render notification follows two rAF callbacks, not independent pixel/speech ground truth. Small samples; nearest-rank p95; no SLA. Missing render includes closed/pinned panel, errors/cancellations and unmatched revisions.',provider_paid_calls=0,live_gate='NOT TESTED',semantic_regression=semantic['result'],hash_format='utf8-lf',source_hashes={p:hashlib.sha256((ROOT/p).read_text('utf-8').encode('utf-8')).hexdigest() for p in paths})
    (EVIDENCE/'review.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:record[k] for k in ('result','final','extension_latency','live_gate')},ensure_ascii=False))


if __name__=='__main__':main()
