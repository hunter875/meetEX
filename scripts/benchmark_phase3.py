"""Deterministic virtual-time replay of the production Service + Provider SSE adapter.

No paid calls. Trigger labels are fixture data, not inferred from model text.
"""
import os
import argparse,asyncio,hashlib,json,math,platform,statistics,sys,tempfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,os.environ.get('MEET_BENCH_BACKEND',str(ROOT/'backend')))
from app.storage import Storage,uid
from app.config import Config
from app.retrieval import Retrieval,Semantic
from app.service import Service
from app.llm import Provider,live_context

class Clock:
    now=0.
    def time(self):return self.now

def stats(values):
    s=sorted(values)
    return dict(n=len(s),median=statistics.median(s) if s else None,p95=s[math.ceil(.95*len(s))-1] if s else None,max=max(s) if s else None)

async def replay(case,clock,folder):
    store=Storage(folder);p=store.create_project(dict(name='Synthetic',description='',glossary={}))
    m=store.create_meeting(dict(project_id=p['id'],title=case['id'],timezone='UTC',persistence_mode='memory',demo=False,meeting_key='/synthetic'))
    db=store.db_for(m['id']);m.update(self_speaker='Me');store.save_meeting(db,m)
    provider=Provider(Config(folder,'FAKE_PAIRING',(),api_key='FAKE_OFFLINE_KEY'),store.settings)
    retrieval=Retrieval(store,Semantic(folder))
    # Keep retrieval synchronous in this virtual-time scheduler experiment. Real
    # threaded retrieval is measured separately using wall-clock concurrency tests.
    service=Service(store,SimpleNamespace(search=retrieval.search,semantic=retrieval.semantic),provider);events=[];attempts=[]
    async def observe(event):events.append(json.loads(json.dumps(event)))
    service.listeners.add(observe)
    async def handler(request):
        wire=json.loads(json.loads(request.content)['messages'][1]['content'])
        running=next((r for r in reversed(store.objects(m['id'],'ai_requests')) if r['status']=='running'),None)
        attempts.append(dict(at=clock.now,request_id=running['id'] if running else None,wire_chars=len(json.dumps(wire,ensure_ascii=False)),repair='validation_feedback' in wire))
        delay=3.0 if case['provider']=='slow' else .3
        await asyncio.sleep(delay)
        if case['provider']=='retry' and len(attempts)==1:return httpx.Response(503)
        if case['provider']=='error':return httpx.Response(401)
        focus=wire.get('focus_segment_ids') or [wire['focus_segment_id']]
        speech=[s for s in wire['segments'] if s['id'] in focus]
        payload=dict(input_revision=wire['transcript_revision'],intent='question',meaning_vi='Cần làm rõ nội dung vừa nói.',findings=[],reply_en='Could you clarify the next step?',reply_vi='Bạn làm rõ bước tiếp theo được không?',clarification_en='',evidence_status='missing',uncertainties=[],supporting_segment_ids=[s['id'] for s in speech])
        if case['provider']=='repair' and len(attempts)==1:payload['input_revision']+=999
        return httpx.Response(200,content='data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(payload)}}]})+'\n\ndata: [DONE]\n\n')
    provider.transport=httpx.MockTransport(handler)
    async def settle():
        for _ in range(15):await asyncio.sleep(0)
    async def advance(target):
        while clock.now<target-.000001:
            clock.now=min(target,round(clock.now+.025,8));await settle()
    origin=clock.now;eligible=[];revisions={};eids={};seen_queries=[];pinned=None
    for n,event in enumerate(case['events']):
        await advance(origin+event['at'])
        op=event['op']
        if op=='caption':
            sid=event.get('segment') or f's{n}';revision=event['revision'];revisions[sid]=revision
            e=dict(type='caption.upsert',protocol_version=1,event_id=uid(),capture_epoch='replay',segment_id=sid,revision=revision,seq=n+1,speaker_label=event['speaker'],text=event['text'],observed_at=(datetime(2026,10,18,tzinfo=timezone.utc)+timedelta(seconds=event['at'])).isoformat(),stable=event.get('stable',True),adapter_version='synthetic-phase3')
            ack=store.apply_caption(m['id'],e)
            if ack['applied']:service.auto(m['id'],e)
            if event['eligible']:eligible.append(dict(id=sid,revision=revision,at=clock.now))
        elif op=='manual':
            body=dict(action=event.get('action','suggest'),question=event['text'])
            if pinned and body['action'] in ('shorter','explain','clarify'):body['base_suggestion_id']=pinned['id']
            service.schedule(m['id'],body)
        elif op=='pin':
            cards=store.objects(m['id'],'suggestions');pinned=cards[-1] if cards else None
        elif op in ('pause','end'):
            service.cancel(m['id']);store.control(m['id'],dict(action=op,idempotency_key=uid()))
        elif op=='source_change':
            current=store.meeting(m['id']);current['context_revision']=current.get('context_revision',0)+1;store.save_meeting(db,current);service.source_changed(p['id'])
        await settle()
    await advance(clock.now+9)
    snapshot=store.snapshot(m['id']);requests=snapshot['requests'];cards=snapshot['suggestions']
    covered=[];waits=[]
    for target in eligible:
        matches=[r for r in requests if r['status'] in ('ready','stale','error','cancelled') and any(s['id']==target['id'] and s['revision']>=target['revision'] for s in r['snapshot']['segments']) and target['id'] in (r['snapshot'].get('focus_segment_ids') or [r['snapshot']['segments'][-1]['id']])]
        covered.append(bool(matches))
        if matches:
            starts=[mark['offset_ms'] for mark in matches[0].get('timing',{}).get('marks',[]) if mark['stage']=='provider_started']
            # Event transcript observed_at and virtual clock share a declared replay origin only.
            matched_ids={r['id'] for r in matches}
            first=next((a['at'] for a in attempts if a['request_id'] in matched_ids and a['at']>=target['at']),None)
            if first is not None:waits.append((first-target['at'])*1000)
    false=0
    for r in requests:
        if r['action']!='auto' or r['status']=='skipped':continue
        focus=r['snapshot'].get('focus_segment_ids') or [r['snapshot']['segments'][-1]['id']]
        if not any(t['id'] in focus for t in eligible):false+=1
    result=dict(id=case['id'],origin_at=origin,split=case['split'],eligible=len(eligible),processed=sum(covered),missed=len(eligible)-sum(covered),false_trigger=false,logical_requests=sum(r['status']!='skipped' for r in requests),http_attempts=len(attempts),repair_attempts=sum(a['repair'] for a in attempts),transient_retry_attempts=max(0,len(attempts)-sum(r['status'] not in ('skipped','superseded') for r in requests)-sum(a['repair'] for a in attempts)),outcomes={status:sum(r['status']==status for r in requests) for status in ('ready','stale','error','cancelled','superseded','skipped','duplicate')},cards=len(cards),ready_cards_proxy=sum(r['status']=='ready' for r in requests),duplicate_cards_same_context=len(cards)-len({(c['snapshot'].get('input_hash'),c['payload']['reply_en']) for c in cards}),wire_chars=stats([a['wire_chars'] for a in attempts]),wire_chars_total=sum(a['wire_chars'] for a in attempts),eligible_wait_ms=stats(waits),usage_known_attempts=sum(r['usage'] is not None for r in provider.metrics),usage_unknown_attempts=sum(r['usage'] is None for r in provider.metrics),tokens=None,cost=None,attempts=[{k:v for k,v in a.items() if k!='wire'} for a in attempts],routes={route:sum(r['snapshot']['routing']['route']==route for r in requests if r['status']!='skipped') for route in ('fast','explain','deep','clarify','listen')},route_latency_ms={route:stats([r.get('duration_ms',0) or 0 for r in requests if r['snapshot']['routing']['route']==route and r['status']!='skipped']) for route in ('fast','explain','deep','clarify')},pinned_action_snapshot_matches=all(r['snapshot']['segments']==pinned['snapshot']['segments'] for r in requests if r['action'] in ('shorter','explain','clarify')) if pinned else None)
    await service.shutdown();await provider.aclose()
    if hasattr(retrieval,'aclose'):await retrieval.aclose()
    store.close();return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--fixture',default='fixtures/phase3/orchestration-replay.json');args=parser.parse_args()
    fixture=ROOT/args.fixture;cases=json.loads(fixture.read_text('utf-8'));clock=Clock()
    loop=asyncio.SelectorEventLoop();loop.time=clock.time
    async def run():
        rows=[]
        with tempfile.TemporaryDirectory(prefix='meet-phase3-') as temporary:
            for n,case in enumerate(cases):rows.append(await replay(case,clock,Path(temporary)/str(n)))
        return rows
    with patch('app.service.time',SimpleNamespace(perf_counter=clock.time,monotonic=clock.time)),patch('app.llm.time',SimpleNamespace(perf_counter=clock.time,monotonic=clock.time)):
        asyncio.set_event_loop(loop)
        try:rows=loop.run_until_complete(run())
        finally:loop.close();asyncio.set_event_loop(None)
    record=dict(mode='synthetic virtual time; production Service + Provider + validators, intercepted SSE; zero paid calls',fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),platform=platform.platform(),policy=getattr(Service,'POLICY_VERSION','baseline-phase2'),config=dict(virtual_tick_ms=25,provider_normal_delay_ms=300,provider_slow_delay_ms=3000,auto_spacing_s=2,input_chars=18000,output_tokens=800,retrieval='synchronous keyword wrapper for both scheduler runs; wall-clock async retrieval measured separately'),rows=rows,totals={key:sum(r[key] for r in rows) for key in ('eligible','processed','missed','false_trigger','logical_requests','http_attempts','repair_attempts','transient_retry_attempts','cards','ready_cards_proxy','wire_chars_total','duplicate_cards_same_context','usage_known_attempts','usage_unknown_attempts')},limitations='Coverage means scheduled focus evidence, not semantic answer quality. Error/cancel/stale counted as processed attempts, reported separately. Ready cards are a publication proxy, not human-rated usefulness. Virtual durations describe deterministic scheduler/provider delay, not CPU or model latency. Tokens/cost unknown without real usage.')
    path=ROOT/args.output;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(record['totals']))

if __name__=='__main__':main()
