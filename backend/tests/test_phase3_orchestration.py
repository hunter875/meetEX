import asyncio
import copy
from dataclasses import replace
from pathlib import Path
import time
import httpx
import pytest
from app.service import Service
from app.retrieval import Retrieval,Semantic
from app.orchestration import decide,meaning_key,TriggerPolicy,retrieval_query
from app.storage import uid
from app.llm import demo_suggestion,live_context
from .conftest import caption
from .test_ai import settle

@pytest.mark.parametrize('text,expected',[("Why?",'direct_question'),('Which environment?','direct_question'),('Why not?','direct_question'),('Hi!','small_talk'),('How are you?','small_talk'),('Thanks!','small_talk'),('Let me finish.','speaker_unfinished'),('Production is blocked.','important_change'),('Yes.','important_change'),('No!','important_change')])
def test_content_policy_short_questions_and_noise(meeting,text,expected):
    m={**meeting,'self_speaker':'Me'};e=caption(text);assert decide(m,e,None,{'Me','Client'})[1]==expected

@pytest.mark.parametrize('before,after',[('We can deploy','We cannot deploy'),('Timeout 15.5 ms API-17','Timeout 50.5 ms API-71'),('Minh owns review','Alex owns review'),('Deadline Friday','Deadline Monday'),('Test staging','Test production')])
def test_critical_corrections_never_cosmetic(meeting,before,after):
    m={**meeting,'self_speaker':'Me'};e=caption(after)
    assert decide(m,e,('Client',meaning_key(before)),{'Me','Client'})==('urgent','meaningful_correction')

@pytest.mark.parametrize('text,own,speaker,reason',[('Why?',None,'Client','speaker_unknown'),('Why?','Me',None,'speaker_unknown'),('Why?','Me','Me','own_turn'),('Alex, why?','Me','Client','other_addressee')])
def test_no_identity_or_addressee_guessing(meeting,text,own,speaker,reason):
    m={**meeting,'self_speaker':own};e=caption(text);e['speaker_label']=speaker
    assert decide(m,e,None,{'Alex','Me','Client'})[1]==reason

def test_policy_and_punctuation_bounds():
    assert meaning_key('  WHY, does this work!  ')==meaning_key('why does this work.')
    assert meaning_key('15.5')!=meaning_key('155')
    assert meaning_key('15 MB')!=meaning_key('15 Mb')
    assert meaning_key('api.prod')!=meaning_key('api prod')
    assert meaning_key('API-17')!=meaning_key('api-17')
    assert meaning_key('/v1/Foo')!=meaning_key('/v1/foo')
    with pytest.raises(ValueError):TriggerPolicy(question_wait_s=9)

class ControlledProvider:
    def __init__(self):self.calls=[];self.gate=asyncio.Event();self.cancelled=0;self.active=0;self.max_active=0
    async def complete(self,snapshot,*args):
        self.calls.append(copy.deepcopy(snapshot))
        self.active+=1;self.max_active=max(self.max_active,self.active)
        try:await self.gate.wait()
        except asyncio.CancelledError:self.cancelled+=1;raise
        finally:self.active-=1
        return demo_suggestion(snapshot)

def configured(store,meeting,provider=None):
    m=store.meeting(meeting['id']);m['self_speaker']='Me';store.save_meeting(store.db_for(m['id']),m)
    return Service(store,Retrieval(store,Semantic(Path('.'))),provider or ControlledProvider())

async def cleanup(service):
    await service.shutdown();await service.retrieval.aclose()

async def test_same_context_singleflight_and_distinct_manual_preempts(store,meeting,request):
    service=configured(store,meeting);id=meeting['id'];store.apply_caption(id,caption('Why is the cache blocked?'))
    a=service.schedule(id,dict(action='suggest'));await settle(lambda:len(service.provider.calls)==1)
    assert service.schedule(id,dict(action='suggest'))==a
    b=service.schedule(id,dict(action='suggest',question='Which environment?'));await settle(lambda:service.provider.cancelled==1)
    assert a!=b;await settle(lambda:len(service.provider.calls)==2)
    service.provider.gate.set();await settle(lambda:len(store.objects(id,'suggestions'))==1)
    assert store.objects(id,'suggestions')[0]['request_id']==b
    assert service.provider.max_active==1;request.node.user_properties.append(('max_active_live_generations','1'))
    await cleanup(service)

async def test_two_questions_plus_ack_focus_all_pending_not_smalltalk(store,meeting):
    service=configured(store,meeting);id=meeting['id'];service.policy=replace(service.policy,question_wait_s=.03)
    for n,text in enumerate(['Why is the cache blocked?','Which environment?','Thanks!']):
        event=caption(text,segment=f's{n}',seq=n+1);store.apply_caption(id,event);service.auto(id,event)
    await settle(lambda:len(service.provider.calls)==1)
    snapshot=service.provider.calls[0];assert snapshot['focus_segment_ids']==['s0','s1'];assert snapshot['routing']['route']!='listen'
    wire=live_context(snapshot);assert len(wire['focus_segment_ids'])==2;assert wire['focus_segment_id']!=wire['segments'][-1]['id']
    service.provider.gate.set();await cleanup(service)

async def test_cosmetic_revision_ignored_but_asked_again_new_id_not_deduped(store,meeting):
    service=configured(store,meeting);id=meeting['id']
    e=caption('Why?',segment='same');store.apply_caption(id,e);service.auto(id,e)
    later=caption('WHY?',segment='same',revision=2,seq=2);store.apply_caption(id,later);service.auto(id,later)
    assert list(service.trigger_metrics)[-1]['reason']=='cosmetic_revision'
    again=caption('Why?',segment='again',seq=3);store.apply_caption(id,again);service.auto(id,again)
    assert service.auto_batches[id]['focus']==['same','again'];await cleanup(service)

async def test_manual_waits_hold_pending_auto_without_replacing_it(store,meeting):
    service=configured(store,meeting);id=meeting['id'];service.policy=replace(service.policy,question_wait_s=.01)
    store.apply_caption(id,caption('Why?'));manual=service.schedule(id,dict(action='suggest'))
    await settle(lambda:len(service.provider.calls)==1)
    e=caption('Which environment?',segment='second',seq=2);store.apply_caption(id,e);service.auto(id,e)
    await asyncio.sleep(.04);assert service.running_requests[id]['id']==manual and id in service.auto_batches
    service.provider.gate.set();await settle(lambda:len(service.provider.calls)==2)
    assert service.provider.calls[-1]['focus_segment_ids']==['second'];await cleanup(service)

@pytest.mark.parametrize('change',[dict(model='other-model'),dict(output_tokens=700),dict(live_timeout_s=12)])
def test_generation_config_is_cache_identity(store,meeting,change):
    service=configured(store,meeting);store.apply_caption(meeting['id'],caption())
    before=service.prepare(meeting['id'],dict(action='suggest'))['input_hash'];store.set_settings(change)
    assert service.prepare(meeting['id'],dict(action='suggest'))['input_hash']!=before

def test_response_mode_and_context_revision_invalidate_cache(store,meeting):
    service=configured(store,meeting);id=meeting['id'];store.apply_caption(id,caption())
    a=service.prepare(id,dict(action='suggest',response_mode='auto'))
    assert a['input_hash']!=service.prepare(id,dict(action='suggest',response_mode='fast'))['input_hash']
    m=store.meeting(id);m['context_revision']=m.get('context_revision',0)+1;store.save_meeting(store.db_for(id),m)
    assert a['input_hash']!=service.prepare(id,dict(action='suggest',response_mode='auto'))['input_hash']

async def test_duplicate_card_only_semantically_identical_same_focus(store,meeting):
    service=configured(store,meeting);id=meeting['id'];service.provider.gate.set()
    e=caption('Why?',segment='s');store.apply_caption(id,e)
    service.schedule(id,dict(action='auto'));await settle(lambda:len(store.objects(id,'suggestions'))==1)
    store.apply_caption(id,caption('Why?',segment='s',revision=2,seq=2))
    second=service.schedule(id,dict(action='auto'));await settle(lambda:next(r for r in store.objects(id,'ai_requests') if r['id']==second)['status']=='duplicate')
    assert len(store.objects(id,'suggestions'))==1
    store.apply_caption(id,caption('Why not?',segment='s',revision=3,seq=3))
    service.schedule(id,dict(action='auto'));await settle(lambda:len(store.objects(id,'suggestions'))==2);await cleanup(service)

def test_whole_turn_context_keeps_anaphora_and_reports_omission(store,meeting):
    service=configured(store,meeting);id=meeting['id']
    for n in range(20):store.apply_caption(id,caption('Historical discussion.',segment=f'h{n}',seq=n+1))
    store.apply_caption(id,caption('Option B uses indexing.',segment='option',seq=21));store.apply_caption(id,caption('What about that option?',segment='focus',seq=22))
    snapshot=service.prepare(id,dict(action='suggest'));assert snapshot['context_omitted_count']>0
    assert {'option','focus'}.issubset({s['id'] for s in snapshot['segments']});assert snapshot['segments'][-1]['text']=='What about that option?'
    query=retrieval_query(snapshot['segments'],focus=['focus']);assert 'Option B uses indexing.' in query
    assert retrieval_query([dict(id='q',text='Why is the cache blocked?'),dict(id='ack',text='Thanks!')],focus=['q'])=='Why is the cache blocked?'

async def test_pause_clears_batch_and_timers(store,meeting):
    service=configured(store,meeting);id=meeting['id'];e=caption('Why?');store.apply_caption(id,e);service.auto(id,e)
    service.cancel(id);store.control(id,dict(action='pause',idempotency_key=uid()));await asyncio.sleep(.2)
    assert not service.provider.calls and id not in service.auto_batches and id not in service.auto_timers
    await cleanup(service)

@pytest.mark.parametrize('new_text,same_segment,ready',[('Thanks!',False,True),('WHY?',True,True),('Why not?',True,False),('Timeout 50 MB',True,False),('Yes.',False,False),('No!',False,False),('OK?',False,False)])
async def test_freshness_allows_only_proven_cosmetic_or_new_smalltalk(store,meeting,new_text,same_segment,ready):
    service=configured(store,meeting);id=meeting['id'];first=caption('Why?',segment='original');store.apply_caption(id,first)
    rid=service.schedule(id,dict(action='suggest'));await settle(lambda:len(service.provider.calls)==1)
    event=caption(new_text,segment='original' if same_segment else 'new',revision=2 if same_segment else 1,seq=2);store.apply_caption(id,event);service.auto(id,event)
    service.provider.gate.set();await settle(lambda:any(s['request_id']==rid for s in store.objects(id,'suggestions')))
    card=next(s for s in store.objects(id,'suggestions') if s['request_id']==rid);assert card['stale']==(not ready)
    if ready:assert next(r for r in store.objects(id,'ai_requests') if r['id']==rid)['timing']['freshness_reason']=='cosmetic_or_new_smalltalk_only'
    await cleanup(service)

async def test_total_generation_timeout_cancels_without_ready(store,meeting):
    service=configured(store,meeting);store.set_settings({'live_timeout_s':.03});id=meeting['id'];store.apply_caption(id,caption('Why?'))
    r=service.schedule(id,dict(action='suggest'));await settle(lambda:any(x['status']=='error' for x in store.objects(id,'ai_requests')))
    assert not store.objects(id,'suggestions');assert service.provider.cancelled==1
    assert next(x for x in store.objects(id,'ai_requests') if x['id']==r)['error']['code']=='PROVIDER_TIMEOUT';await cleanup(service)

def test_http_attempt_retry_repair_and_usage_are_correlated(client):
    import json
    from .test_phase1_pipeline import real_meeting,sse
    project,meeting=real_meeting(client,[('Me','Let us review.'),('Client','Why is the cache blocked?')]);id=meeting['id']
    assert client.patch('/api/v1/meetings/'+id,json={'self_speaker':'Me'}).status_code==200
    calls=[]
    async def handler(request):
        wire=json.loads(json.loads(request.content)['messages'][1]['content']);calls.append(wire)
        assert 'logical_request_id' not in json.dumps(wire)
        if len(calls)==1:return httpx.Response(503)
        payload=dict(input_revision=wire['transcript_revision']+(1 if len(calls)==2 else 0),intent='question',meaning_vi='Cần làm rõ.',findings=[],reply_en='Could you clarify?',reply_vi='Bạn làm rõ được không?',clarification_en='',evidence_status='missing',uncertainties=[],supporting_segment_ids=[s['id'] for s in wire['segments']])
        return sse(payload)
    client.app.state.provider.transport=httpx.MockTransport(handler)
    rid=client.post('/api/v1/meetings/'+id+'/suggest',json={'action':'auto'}).json()['request_id']
    for _ in range(200):
        requests=client.get('/api/v1/meetings/'+id).json()['requests'];r=next(r for r in requests if r['id']==rid)
        if r['status']=='ready':break
        time.sleep(.01)
    assert r['status']=='ready' and len(calls)==3
    records=client.get('/api/v1/metrics').json()['records'];mine=[a for a in records if a['logical_request_id']==rid]
    assert [a['attempt_reason'] for a in mine]==['initial','transient_retry','repair']
    assert r['timing']['http_attempts']==3 and r['timing']['repair_attempts']==1 and r['timing']['usage_unknown_attempts']==3
    assert len(client.app.state.service.rate[id])==1


def test_virtual_clock_no_starvation_and_fast_question_interrupts_batch(tmp_path):
    from scripts.benchmark_phase3 import Clock,replay
    from types import SimpleNamespace
    from unittest.mock import patch
    import json
    cases=json.loads(Path('fixtures/phase3/orchestration-replay.json').read_text('utf-8'))
    burst=next(c for c in cases if c['id']=='stable-correction-burst')
    short=dict(id='urgent-within-batch',split='test',provider='normal',events=[dict(at=0,text='Here is some relevant information about the project.',speaker='Client',segment='info',revision=1,eligible=False,op='caption'),dict(at=.1,text='Why?',speaker='Client',segment='why',revision=1,eligible=True,op='caption')])
    clock=Clock();loop=asyncio.SelectorEventLoop();loop.time=clock.time
    with patch('app.service.time',SimpleNamespace(perf_counter=clock.time,monotonic=clock.time)),patch('app.llm.time',SimpleNamespace(perf_counter=clock.time,monotonic=clock.time)):
        asyncio.set_event_loop(loop)
        try:
            a=loop.run_until_complete(replay(burst,clock,tmp_path/'burst'));origin=clock.now
            b=loop.run_until_complete(replay(short,clock,tmp_path/'short'))
        finally:loop.close();asyncio.set_event_loop(None)
    assert a['attempts'][0]['at']<=2.025 and a['http_attempts']==2 and a['missed']==0
    assert b['attempts'][0]['at']-origin<=.275 and b['missed']==0

async def test_preparing_manual_is_singleflight_latest_wins_and_auto_cannot_replace_it(store,meeting):
    service=configured(store,meeting);id=meeting['id'];store.apply_caption(id,caption('Why?'));gate=asyncio.Event();calls=[]
    async def retrieve(project,query):calls.append(query);await gate.wait();return dict(results=[],duration_ms=1,index_generation={})
    service.retrieval.search_async=retrieve
    a=asyncio.create_task(service.schedule_async(id,dict(action='suggest',question='First')));await asyncio.sleep(0);await asyncio.sleep(0)
    b=asyncio.create_task(service.schedule_async(id,dict(action='suggest',question='Second')));c=asyncio.create_task(service.schedule_async(id,dict(action='suggest',question='Second')))
    await asyncio.sleep(.01)
    auto=asyncio.create_task(service.schedule_async(id,dict(action='auto')));gate.set()
    from app.errors import AppError
    with pytest.raises(AppError) as error:await a
    assert error.value.code=='PREPARATION_SUPERSEDED'
    rid,duplicate,held=await asyncio.gather(b,c,auto);assert rid==duplicate==held
    await settle(lambda:len(service.provider.calls)==1);assert service.provider.calls[0]['question']=='Second'
    assert len(store.objects(id,'ai_requests'))==1;await cleanup(service)

async def test_retrieval_deadline_never_launches_provider(store,meeting):
    service=configured(store,meeting);id=meeting['id'];store.apply_caption(id,caption('Why?'));service.policy=replace(service.policy,retrieval_timeout_s=.02)
    async def stalled(*args):await asyncio.Event().wait()
    service.retrieval.search_async=stalled
    from app.errors import AppError
    with pytest.raises(AppError) as error:await service.schedule_async(id,dict(action='suggest'))
    assert error.value.code=='RETRIEVAL_TIMEOUT' and not service.provider.calls and not service.preparing
    await cleanup(service)

async def test_finish_cue_suspends_pending_until_new_stable_content(store,meeting):
    service=configured(store,meeting);id=meeting['id'];service.policy=replace(service.policy,question_wait_s=.02)
    for n,text in enumerate(['Why?','Let me finish.']):
        e=caption(text,segment=f's{n}',seq=n+1);store.apply_caption(id,e);service.auto(id,e)
    await asyncio.sleep(.06);assert not service.provider.calls and service.auto_batches[id]['blocked']
    e=caption('Which environment?',segment='s2',seq=3);store.apply_caption(id,e);service.auto(id,e)
    await settle(lambda:len(service.provider.calls)==1);assert service.provider.calls[0]['focus_segment_ids']==['s0','s2'];await cleanup(service)

@pytest.mark.parametrize('action',['pause','end'])
async def test_session_control_cancels_context_preparation_without_provider(store,meeting,action):
    service=configured(store,meeting);id=meeting['id'];store.apply_caption(id,caption('Why?'));started=asyncio.Event()
    async def stalled(*args):started.set();await asyncio.Event().wait()
    service.retrieval.search_async=stalled
    work=asyncio.create_task(service.schedule_async(id,dict(action='suggest')));await started.wait()
    service.cancel(id);store.control(id,dict(action=action,idempotency_key=uid()))
    from app.errors import AppError
    with pytest.raises(AppError):await work
    assert not service.provider.calls and not store.objects(id,'suggestions');await cleanup(service)
