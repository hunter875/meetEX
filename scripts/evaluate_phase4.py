"""Paired ledger/state and controlled long-report evaluation. No paid calls."""
import argparse,asyncio,hashlib,json,math,os,platform,re,statistics,sys,tempfile,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,os.environ.get('MEET_PHASE4_BACKEND',str(ROOT/'backend')))
from app.storage import Storage,uid
from app.service import Service
from app.retrieval import Retrieval,Semantic
from app.llm import Provider
from app.config import Config

def stats(values):
    values=sorted(values);return dict(n=len(values),median_ms=statistics.median(values) if values else None,p95_ms=values[math.ceil(.95*len(values))-1] if values else None,max_ms=max(values) if values else None)
def event(e,n):return dict(type='caption.upsert',protocol_version=1,event_id=uid(),capture_epoch='phase4-eval',segment_id=e['segment'],revision=e['revision'],seq=n+1,speaker_label=e['speaker'],text=e['text'],stable=e['stable'],observed_at=e['observed_at'],adapter_version='synthetic-phase4')
def make(store,title):
    project=store.create_project(dict(name=title,description='',glossary={}));return store.create_meeting(dict(project_id=project['id'],title=title,timezone='America/Los_Angeles',persistence_mode='memory',demo=False))
def item(text,id,section='decisions',owner=None,due=None):return dict(id=id,text=text,text_en=text,evidence_segment_ids=[id],origin='transcript',confirmation='confirmed' if section in ('decisions','action_items') else 'unconfirmed',owner=owner,raw_due_text=due,normalized_due=due if due and due[:4].isdigit() else None,status='open')

async def long_report(store):
    m=make(store,'Long controlled cross-map');changes={0:('Client','Confirmed: deploy API-17 on Friday.'),80:('Minh','I will review API-18 by 2026-10-22.'),160:('Client','Correction: confirmed deploy API-17 on Monday instead.'),240:('Minh','Correction: I will review API-18 by 2026-10-26 instead.'),320:('Client','Cancel deploy API-17 because QA is not finished.')}
    timings=[]
    for n in range(321):
        speaker,text=changes.get(n,('Client','Ordinary discussion of observations; no acceptance or deadline. '*9))
        e=dict(segment=f'long-{n}',revision=1,speaker=speaker,text=text,stable=True,observed_at='2026-10-19T00:30:00Z');began=time.perf_counter();store.apply_caption(m['id'],event(e,n));timings.append((time.perf_counter()-began)*1000)
    provider=Provider(Config(store_path(store),'FAKE_PAIRING',(),api_key='FAKE_PHASE4_OFFLINE_KEY'),store.settings);attempts=[]
    async def handler(request):
        wire=json.loads(json.loads(request.content)['messages'][1]['content']);attempts.append(wire);await asyncio.sleep(.005)
        payload=dict(summary_vi='Controlled map of observed speech.',summary_en='Controlled map of observed speech.',summary_segment_ids=[s['id'] for s in wire['segments']],requirements=[],decisions=[],action_items=[],open_questions=[],ai_proposals=[],capture_warnings=[])
        for segment in wire['segments']:
            id=segment['id'];text=segment['text']
            if id in ('long-0','long-160'):payload['decisions'].append(item(text,id))
            elif id in ('long-80','long-240'):payload['action_items'].append(item(text,id,'action_items','Minh','2026-10-22' if id=='long-80' else '2026-10-26'))
            elif id=='long-320':payload['open_questions'].append(item(text,id,'open_questions'))
        return httpx.Response(200,content='data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(payload)}}]})+'\n\ndata: [DONE]\n\n')
    provider.transport=httpx.MockTransport(handler);service=Service(store,Retrieval(store,Semantic(ROOT/'.local/models')),provider)
    store.control(m['id'],dict(action='end',idempotency_key=uid()));began=time.perf_counter();job=service.report(m['id'],store.meeting(m['id'])['transcript_revision'])
    while job['status'] in ('queued','running'):await asyncio.sleep(.001)
    elapsed=(time.perf_counter()-began)*1000;report=service.get_report(job['report_id']) if job['status']=='ready' else None
    result=dict(turns=321,maps=len(service.report_chunks(store.transcript(m['id']))),provider_mode='actual Provider SSE adapter, MockTransport, 5 ms controlled delay; no model extraction quality',http_attempts=len(attempts),retry_attempts=sum(r.get('http_attempt',1)>1 for r in provider.metrics),repair_attempts=sum(r.get('generation_attempt',1)>1 for r in provider.metrics),usage_unknown_attempts=sum(r.get('usage') is None for r in provider.metrics),real_tokens=None,real_cost=None,status=job['status'],error=job.get('error'),latency_ms=elapsed,caption_apply=stats(timings),final_report=report)
    result['memory_update']=stats(getattr(store,'memory_update_timings',[]))
    if report:
        result['expired_confirmed_decisions_current']=sum('API-17' in i['text'] for i in report['payload']['decisions'])
        result['expired_deadlines_current']=sum(i.get('raw_due_text')=='2026-10-22' for i in report['payload']['action_items'])
        summary=report['payload']['summary_en']
        result['summary_current_cancellation_covered']='cancelled' in summary
        result['summary_contradicts_final']=bool(('Friday' in summary or '2026-10-22' in summary) and re.search(r'confirmed|accepted|will',summary,re.I))
    await service.shutdown();await provider.aclose();await service.retrieval.aclose();return result

def store_path(store):return Path(store.disk.execute('PRAGMA database_list').fetchone()['file']).parent

async def run(output,split):
    fixture=ROOT/'fixtures/phase4/meeting-memory.json';corpus=json.loads(fixture.read_text('utf8'));cases=[c for c in corpus['cases'] if split=='all' or c['split']==split];results=[];fields=('kind','entity','status','owner','normalized_due','environment')
    with tempfile.TemporaryDirectory(prefix='meet-phase4-') as tmp:
      for case in cases:
        store=Storage(Path(tmp)/case['id']);m=make(store,case['id']);timings=[]
        if case.get('gap'):
            with store.db_for(m['id']):store.gap(store.db_for(m['id']),m['id'],'sequence_gap',certainty='possible')
        for n,e in enumerate(case['events']):
            began=time.perf_counter();store.apply_caption(m['id'],event(e,n));timings.append((time.perf_counter()-began)*1000)
        actual=store.memory(m['id']) if hasattr(store,'memory') else [];expected=case['expected'];remaining=list(actual);correct=0;wrong=0;missed=0;field_counts={key:dict(correct=0,wrong=0,missing=0) for key in fields[2:]}
        evidence_correct=0;expected_refs=[dict(segment_id=e['segment'],revision=e['revision']) for e in case['events']]
        if case['id']=='correction-NOT':expected_refs=[expected_refs[-1]]
        if case['id']=='two-tasks-one-turn':expected_refs=[expected_refs[0],expected_refs[0]]
        if len(expected_refs)==1 and len(expected)>1:expected_refs=expected_refs*len(expected)
        for index,gold in enumerate(expected):
            candidate=next((i for i in remaining if all(i.get(k)==gold[k] for k in fields[:2]) and i.get('environment')==gold['environment']),None)
            if candidate is None:
                missed+=1
                for k in field_counts:field_counts[k]['missing']+=1
                continue
            remaining.remove(candidate);ok=all(candidate.get(k)==gold[k] for k in fields);correct+=ok;wrong+=not ok
            for k in field_counts:field_counts[k]['correct' if candidate.get(k)==gold[k] else 'wrong']+=1
            refs=candidate['evidence'];valid=all(store.evidence_revision(m['id'],r['segment_id'],r['revision']) for r in refs)
            evidence_correct+=bool(valid and expected_refs[index] in refs)
        results.append(dict(id=case['id'],split=case['split'],expected_items=len(expected),correct_items=correct,wrong_items=wrong,missing_items=missed,extra_items=len(remaining),field_counts=field_counts,evidence_correct=evidence_correct,evidence_expected=len(expected),caption_apply=stats(timings),items=actual))
        store.close()
      store=Storage(Path(tmp)/'long');long=await long_report(store);store.close()
    record=dict(platform=platform.platform(),python=sys.version,baseline_commit='af868491a77a168e3ab68b457bb6a10c65f0c3f7',mode='controlled synthetic; no paid calls',structured_ledger_available=hasattr(Storage,'memory'),fixture_sha256=hashlib.sha256(fixture.read_text('utf8').encode()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_text('utf8').encode()).hexdigest(),split=split,cases=results,totals={k:sum(r[k] for r in results) for k in ('expected_items','correct_items','wrong_items','missing_items','extra_items','evidence_correct','evidence_expected')},long_report=long,real_model_quality='NOT TESTED',paid_calls=0)
    (ROOT/output).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in record.items() if k in ('totals','structured_ledger_available','real_model_quality')}));print(json.dumps({k:v for k,v in long.items() if k!='final_report'}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--split',choices=['tuning','evaluation','all'],default='all');args=parser.parse_args();asyncio.run(run(args.output,args.split))
