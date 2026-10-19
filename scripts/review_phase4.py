"""Audit final evidence. Fixture scores are not general model accuracy."""
from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];E=ROOT/'docs/evidence/phase4'
def read(name):return json.loads((E/name).read_text('utf8'))
before,after=read('evaluation-baseline.json'),read('evaluation-after.json')
assert before['fixture_sha256']==after['fixture_sha256'] and before['harness_sha256']==after['harness_sha256']
assert after['totals']['correct_items']==after['totals']['expected_items']==38
assert after['totals']['wrong_items']==after['totals']['missing_items']==after['totals']['extra_items']==0
assert after['totals']['evidence_correct']==38
gold=json.loads((ROOT/'fixtures/phase4/meeting-memory.json').read_text('utf8'))['cases']
counts=dict(owner_expected=0,owner_correct=0,owner_wrong=0,false_owner=0,normalized_due_expected=0,normalized_due_correct=0,normalized_due_wrong=0,false_normalized_due=0,confirmed_or_accepted_expected=0,confirmed_or_accepted_correct=0,false_confirmation=0)
relation_gold={'deadline-replaced':[(0,'superseded_by',1)],'cancelled':[(0,'accepted_by',1),(1,'superseded_by',2),(2,'cancelled_by',3),(3,'cancels',2)],'owner-takeover':[(0,'superseded_by',1)],'disagreement':[(0,'disputed_by',1),(1,'disputes',0)],'long-cross-map':[(0,'superseded_by',1),(1,'cancelled_by',2),(2,'cancels',1)],'done':[(0,'completed_by',1)]}
relations=dict(expected=0,correct=0,wrong=0,extra=0)
for expected,actual in zip(gold,after['cases']):
    assert expected['id']==actual['id'] and len(expected['expected'])==len(actual['items'])
    for g,a in zip(expected['expected'],actual['items']):
        for field,prefix in (('owner','owner'),('normalized_due','normalized_due')):
            if g[field] is not None:
                counts[prefix+'_expected']+=1;counts[prefix+'_correct' if g[field]==a[field] else prefix+'_wrong']+=1
            elif a[field] is not None:counts['false_'+prefix]+=1
        confirmed=g['kind']=='decision' and g['status']=='confirmed' or g['kind']=='action_item' and g['status'] in ('accepted','completed')
        predicted=a['kind']=='decision' and a['status']=='confirmed' or a['kind']=='action_item' and a['status'] in ('accepted','completed')
        if confirmed:counts['confirmed_or_accepted_expected']+=1;counts['confirmed_or_accepted_correct']+=predicted
        elif predicted:counts['false_confirmation']+=1
    expected_edges={(actual['items'][i]['id'],t,actual['items'][j]['id']) for i,t,j in relation_gold.get(actual['id'],[])}
    actual_edges={(item['id'],edge['type'],edge['item_id']) for item in actual['items'] for edge in item['relations']}
    relations['expected']+=len(expected_edges);relations['correct']+=len(expected_edges&actual_edges);relations['wrong']+=len(expected_edges-actual_edges);relations['extra']+=len(actual_edges-expected_edges)
assert relations['wrong']==relations['extra']==0,relations
long=after['long_report'];assert long['status']=='ready' and long['maps']>=10 and long['expired_confirmed_decisions_current']==long['expired_deadlines_current']==0
assert long['summary_current_cancellation_covered'] and not long['summary_contradicts_final']
tree=ET.parse(E/'backend-final.xml').getroot();assert all(int(s.get('failures',0))==int(s.get('errors',0))==0 for s in tree.iter('testsuite'))
front,browser=read('frontend-final.json'),read('browser-final-results.json');assert front['numFailedTests']==0 and browser['stats']['unexpected']==0 and browser['stats']['expected']==6
semantic=read('semantic-regression.json');assert semantic['result']=='PASS' and all(p['blocked'] for p in semantic['original_probes'])
paths=subprocess.check_output(['git','diff','--name-only','af86849'],cwd=ROOT,text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
paths=sorted({p for p in paths if p.startswith(('backend/','extension/','e2e/','scripts/','fixtures/phase4/')) and Path(p).suffix in ('.py','.sql','.ts','.tsx','.js','.json')})
record=dict(result='PARTIAL: verified bounded grammar/controlled pipeline; broader semantic linking and real model/live evaluation remain open',client_date='2026-10-19',timezone='America/Los_Angeles',base_commit='af868491a77a168e3ab68b457bb6a10c65f0c3f7',starting_branch='codex/phase3-orchestration',starting_tree='clean',branch='codex/phase4-meeting-memory',areas={'A':'PARTIAL: typed evidence/version model PASS; extraction grammar limited','B':'PARTIAL: explicit transitions PASS; bare Yes/authority/coreference unresolved','C':'PASS controlled live scope, budget, revision/cache/guard tests','D':'PARTIAL: controlled cross-map current/history PASS; general summary completeness not established','E':'PASS automated UI/edit/history/export scope','F':'PASS labelled synthetic audit; not general accuracy'},fixture_sha256=after['fixture_sha256'],harness_sha256=after['harness_sha256'],item_quality=after['totals'],field_quality=counts,relation_quality=relations,relations_label_note='State/item labels predeclared before implementation. Edge assertions added after initial grammar draft; not a held-out relation benchmark.',splits={split:{k:sum(c[k] for c in after['cases'] if c['split']==split) for k in ('expected_items','correct_items','wrong_items','missing_items','extra_items','evidence_correct')} for split in ('tuning','evaluation')},regression=dict(backend=len(list(tree.iter('testcase'))),frontend=front['numPassedTests'],browser=6,semantic='PASS'),long_before={k:v for k,v in before['long_report'].items() if k!='final_report'},long_after={k:v for k,v in long.items() if k!='final_report'},provider_paid_calls=0,real_model_quality='NOT TESTED',live_meet='NOT TESTED',hash_format='utf8-lf',source_hashes={p:hashlib.sha256((ROOT/p).read_text('utf8').encode()).hexdigest() for p in paths},limitations=['23 short synthetic scenarios, 18 tuning/5 held-out variants; 38 items, not human-meeting accuracy. Separate 321-turn controlled report is a pipeline test, not hours-long real meeting.','Bare Yes does not bind an owner even with a plausible antecedent; unbound denial requests clarification. Explicit IDs/actions/environment dominate automatic linking.','Structured source facts remain in project retrieval; AI proposals stay distinct; no summary becomes evidence. User-edit ledger is exported separately, not recertified as participant speech.','No general paraphrase, authority or multilingual extraction. Unrecognized map claims retain Phase 1 validators, which do not prove general entailment.','Revision-strict memory may stale extra generations compared with Phase 3 cosmetic handling; no new real provider latency/cost measurement.'])
(E/'review.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:record[k] for k in ('result','item_quality','field_quality','relation_quality','splits','regression')},ensure_ascii=False))
