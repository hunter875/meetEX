"""Audit predeclared objectives without rewriting them after tuning."""
import hashlib,json,subprocess,sys,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];E=ROOT/'docs/evidence/phase3'
def read(name):return json.loads((E/name).read_text('utf-8'))

def main():
    before,after=read('orchestration-baseline.json'),read('orchestration-after.json')
    assert before['fixture_sha256']==after['fixture_sha256'] and before['harness_sha256']==after['harness_sha256']
    assert before['config']==after['config'] and len(before['rows'])==len(after['rows'])
    assert after['totals']['eligible']==before['totals']['eligible']==39
    assert after['totals']['missed']==0 and after['totals']['false_trigger']==0
    b,a=before['totals'],after['totals']
    before_context=next(r for r in before['rows'] if r['id']=='context-budget')['wire_chars_total']
    after_context=next(r for r in after['rows'] if r['id']=='context-budget')['wire_chars_total']
    short_ids=('short-questions','heldout-short','asked-again','two-questions','slow-manual')
    short_wait=max(r['eligible_wait_ms']['max'] or 0 for r in after['rows'] if r['id'] in short_ids)
    targets=read('targets.json')['targets']
    objectives=dict(mandatory_eligible_missed=dict(actual=a['missed'],target=0,passed=a['missed']==0),false_triggers_reduction_fraction_min=dict(actual=1-a['false_trigger']/b['false_trigger'],target=targets['false_triggers_reduction_fraction_min'],passed=(1-a['false_trigger']/b['false_trigger'])>=targets['false_triggers_reduction_fraction_min']),logical_requests_reduction_fraction_min=dict(actual=1-a['logical_requests']/b['logical_requests'],target=targets['logical_requests_reduction_fraction_min'],passed=(1-a['logical_requests']/b['logical_requests'])>=targets['logical_requests_reduction_fraction_min']),short_question_schedule_wait_max_ms=dict(actual=short_wait,target=targets['short_question_schedule_wait_max_ms'],passed=short_wait<=targets['short_question_schedule_wait_max_ms']),context_fixture_wire_reduction_fraction_min=dict(actual=1-after_context/before_context,target=targets['context_fixture_wire_reduction_fraction_min'],passed=(1-after_context/before_context)>=targets['context_fixture_wire_reduction_fraction_min']))
    backend=ET.parse(E/'backend-final.xml').getroot();assert all(int(s.get('failures',0))==int(s.get('errors',0))==0 for s in backend.iter('testsuite'))
    cases=list(backend.iter('testcase'));names={c.get('name') for c in cases}
    assert 'test_virtual_clock_no_starvation_and_fast_question_interrupts_batch' in names
    assert any(p.get('name')=='max_active_live_generations' and p.get('value')=='1' for p in backend.iter('property'))
    burst=next(r for r in after['rows'] if r['id']=='stable-correction-burst')
    first_batch_ms=(burst['attempts'][0]['at']-burst['origin_at'])*1000
    objectives['nonstarvation_max_batch_wait_ms']=dict(actual=first_batch_ms,target=2000,passed=first_batch_ms<=2000.000001,evidence='production virtual replay; first bounded batch during continuous stable revisions')
    objectives['single_live_provider_generation_max']=dict(actual=1,target=1,passed=True,evidence='max_active_live_generations JUnit property')
    front=read('frontend-final.json');browser=read('browser-final-results.json')
    assert front['numFailedTests']==0 and browser['stats']['unexpected']==0 and browser['stats']['expected']==5
    semantics=read('semantic-regression.json');assert semantics['result']=='PASS' and all(p['blocked'] for p in semantics['original_probes'])
    rb,ra=read('retrieval-baseline.json'),read('retrieval-after.json')
    for x,y in zip(rb['rows'],ra['rows']):assert x['mode']==y['mode'] and x['hit_top5']==y['hit_top5']
    splits={split:{k:sum(r[k] for r in after['rows'] if r['split']==split) for k in ('eligible','processed','missed','false_trigger','logical_requests','http_attempts')} for split in ('tuning','evaluation')}
    lifecycle=read('lifecycle-after.json');assert all(r['pinned_action_snapshot_matches'] for r in lifecycle['rows'])
    paths=subprocess.check_output(['git','diff','--name-only','bccc6f5bbb94711ae71e13c654b65dfe687940c3'],cwd=ROOT,text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    paths=sorted(set(p for p in paths if p.startswith(('backend/','extension/','e2e/','scripts/','fixtures/phase3/')) and Path(p).suffix in ('.py','.ts','.tsx','.js','.json')))
    record=dict(result='PARTIAL: controlled improvements verified; two predeclared targets unmet' if not all(o['passed'] for o in objectives.values()) else 'PASS controlled scope',client_date='2026-10-18',timezone='America/Los_Angeles',base_commit='bccc6f5bbb94711ae71e13c654b65dfe687940c3',initial_branch='codex/phase2-capture',initial_worktree='clean',branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),reference_commits={'tfp24601/live-meeting-assistant':'47d518101023300b1a8feeaaa7f56a3c69cd53c6','krystiangw/meet-live-assist-extension':'c26b04e6eb875a44536bed5afb3e80ce49b56ff1'},objectives=objectives,baseline=b,after=a,heldout=splits,regression=dict(backend=len(cases),frontend=front['numPassedTests'],browser=5,semantic=semantics['result']),paid_provider_calls=0,real_provider_benchmark='NOT TESTED',live_meet='NOT TESTED',tokens_cost='Unknown; no real usage. Estimates explicitly labelled, cancelled attempts not free.',hash_format='utf8-lf',source_hashes={p:hashlib.sha256((ROOT/p).read_text('utf-8').encode('utf-8')).hexdigest() for p in paths},limitations='31 synthetic scenarios with 4 held-out variants; controlled output quality/ready is a publication proxy. Real E5 tested only on existing 12-chunk demo; 100/1000/10000 vector scaling is controlled. Timing samples small; cold/warm/cache hits separated. Manual priority can exceed 500 ms Auto wait; request reduction remains below 20% target.')
    (E/'review.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:record[k] for k in ('result','objectives','regression','heldout')},ensure_ascii=False))
if __name__=='__main__':main()
