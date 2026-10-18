import asyncio
import json
from pathlib import Path
import httpx
import pytest
from pydantic import ValidationError
from app.config import Config
from app.llm import Provider,SuggestionPayload,ReportPayload,validate_suggestion,validate_report,demo_suggestion,live_context
from app.retrieval import Retrieval,Semantic
from app.service import Service
from app.storage import uid,dumps
from app.errors import AppError
from .conftest import caption

def context():return dict(transcript_revision=1,segments=[{'id':'s','text':'We will NOT deploy on Friday. Maybe Monday.'}],sources=[])
def payload():return demo_suggestion(context()).model_dump()

@pytest.mark.acceptance('AI-01','AI-03','AI-04','AI-08')
def test_ai_validation_rejects_extra_enum_unknown_ids_and_contradictory_commitment():
    p=payload();validate_suggestion(SuggestionPayload(**p),context())
    for patch in ({'extra':'no'},{'intent':'invented'},{'reply_en':''}):
        with pytest.raises(ValidationError):SuggestionPayload(**{**p,**patch})
    for patch in ({'supporting_segment_ids':['other-project']},{'input_revision':44},{'evidence_status':'supported'},{'findings':[{'text_vi':'Fabricated','source_ids':['missing']} ]},{'reply_en':'We will deploy on Friday.'}):
        with pytest.raises(AppError):validate_suggestion(SuggestionPayload(**{**p,**patch}),context())

@pytest.mark.acceptance('AI-01','AI-02','REP-03')
def test_report_requires_actual_evidence_owner_and_confirmed_dates():
    seg=[{'id':'s','text':'We will NOT deploy on Friday. Maybe Monday.'}]
    base=dict(id='action',text='Deploy on Friday',evidence_segment_ids=['s'],origin='transcript',confirmation='confirmed')
    for change,section in [({},'action_items'),({'text':'Schedule Monday','raw_due_text':'Monday'},'action_items'),({'text':'Check status','owner':'Alice'},'action_items'),({'text':'We confirm Monday'},'decisions'),({'text':'X','evidence_segment_ids':['invented']},'requirements')]:
        with pytest.raises(AppError):validate_report(ReportPayload(**{section:[{**base,**change}]}),seg)
    valid=ReportPayload(open_questions=[dict(id='q',text='When will we deploy?',evidence_segment_ids=['s'],origin='transcript',confirmation='unconfirmed',owner=None,raw_due_text=None)])
    validate_report(valid,seg)
    assert valid.open_questions[0].owner is None and valid.open_questions[0].raw_due_text is None
    with pytest.raises(AppError):validate_report(ReportPayload(requirements=[dict(id='x',text='AI guessed this',origin='ai_proposal',evidence_segment_ids=[])]),seg)

@pytest.mark.acceptance('AI-02','REP-03')
def test_confirmed_staging_decision_survives_separate_production_denial():
    def decision(text):
        return ReportPayload(decisions=[dict(id='d',text=text,evidence_segment_ids=['s'],origin='transcript',confirmation='confirmed')])
    validate_report(decision('Chỉ kiểm thử staging; production chưa được duyệt.'),[
        dict(id='s',text='Confirmed: we will test in staging only. Production deployment is not approved.')])
    for text in ('Production deployment is not approved.', 'We cannot confirm the deployment.', 'We will not approve production.'):
        with pytest.raises(AppError):validate_report(decision('Production được duyệt.'),[dict(id='s',text=text)])

@pytest.mark.acceptance('AI-02','REP-03')
def test_report_owner_from_named_speaker_first_person_acceptance():
    report=ReportPayload(action_items=[dict(id='a',text='Minh điều tra định dạng CSV.',evidence_segment_ids=['s'],origin='transcript',confirmation='confirmed',owner='Minh')])
    validate_report(report,[dict(id='s',speaker='Minh',text='I will investigate the CSV formatting.')])
    for speaker,text in [('Alex','I will investigate the CSV formatting.'),('Minh','We will investigate the CSV formatting.'),('Minh','I will not investigate the CSV formatting.')]:
        with pytest.raises(AppError):validate_report(report,[dict(id='s',speaker=speaker,text=text)])

@pytest.mark.acceptance('REP-03')
def test_report_cannot_silently_drop_an_explicit_first_person_commitment():
    segments=[dict(id='investigate',speaker='Minh',text='I will investigate the CSV export formatting.')]
    with pytest.raises(AppError) as error:validate_report(ReportPayload(summary_vi='Cần kiểm tra CSV.',summary_segment_ids=['investigate']),segments)
    assert error.value.code=='REPORT_COVERAGE' and error.value.extra['segment_ids']==['investigate']
    validate_report(ReportPayload(action_items=[dict(id='a',text='Minh điều tra định dạng CSV.',evidence_segment_ids=['investigate'],origin='transcript',owner='Minh',confirmation='confirmed')]),segments)

@pytest.mark.acceptance('OPS-01','SEC-06','AI-07','OPS-03')
async def test_provider_stream_usage_no_secret_in_prompt_and_401_no_retry(tmp_path,store):
    config=Config(tmp_path,'pair',(),api_key='SECRET_KEY_SENTINEL')
    provider=Provider(config,store.settings);requests=[]
    async def handler(request):
        requests.append(request)
        body=json.loads(request.content)
        assert 'SECRET_KEY_SENTINEL' not in request.content.decode()
        assert body['thinking']=={'type':'disabled'} and 'tools' not in body
        assert request.headers['Authorization']=='Bearer SECRET_KEY_SENTINEL'
        if len(requests)==1:return httpx.Response(401,json={'error':'SECRET_KEY_SENTINEL'})
        wire_payload={**payload(),'supporting_segment_ids':[json.loads(body['messages'][1]['content'])['segments'][0]['id']]}
        stream='data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(wire_payload)}}]})+'\n\ndata: '+json.dumps({'choices':[],'usage':{'prompt_tokens':8,'completion_tokens':12}})+'\n\ndata: [DONE]\n\n'
        return httpx.Response(200,content=stream,headers={'Content-Type':'text/event-stream'})
    provider.transport=httpx.MockTransport(handler)
    with pytest.raises(AppError) as e:await provider.complete(context(),SuggestionPayload)
    assert e.value.code=='PROVIDER_AUTH' and len(requests)==1
    assert 'SECRET_KEY_SENTINEL' not in dumps(e.value.payload())+dumps(provider.metrics)
    output=await provider.complete(context(),SuggestionPayload)
    validate_suggestion(output,context())
    assert provider.metrics[-1]['usage']['completion_tokens']==12
    assert provider.metrics[-1]['first_token_ms'] is not None

@pytest.mark.acceptance('OPS-01','AI-08')
async def test_provider_malformed_json_and_transient_retry_are_bounded(tmp_path,store):
    provider=Provider(Config(tmp_path,'pair',(),api_key='fake'),store.settings);calls=[]
    async def handler(request):
        calls.append(1)
        if len(calls)==1:return httpx.Response(503)
        return httpx.Response(200,content='data: '+json.dumps({'choices':[{'delta':{'content':'{bad JSON'}}]})+'\n\ndata: [DONE]\n\n')
    provider.transport=httpx.MockTransport(handler)
    with pytest.raises(AppError) as e:await provider.complete(context(),SuggestionPayload)
    assert e.value.code=='AI_SCHEMA' and len(calls)==2
    assert provider.metrics[-1]['usage'] is None

@pytest.mark.acceptance('OPS-01')
async def test_provider_timeout_does_not_silently_start_second_generation(tmp_path,store):
    store.set_settings({'live_timeout_s':.015});provider=Provider(Config(tmp_path,'pair',(),api_key='fake'),store.settings)
    calls=[]
    async def handler(request):calls.append(1);await asyncio.sleep(.1);return httpx.Response(200)
    provider.transport=httpx.MockTransport(handler)
    with pytest.raises(AppError) as e:await provider.complete(context(),SuggestionPayload)
    assert e.value.code=='PROVIDER_TIMEOUT' and len(calls)==1

@pytest.mark.acceptance('OPS-01','OPS-03','SEC-06')
async def test_provider_reuses_client_but_uses_current_credential_and_closes_pool(tmp_path,store):
    provider=Provider(Config(tmp_path,'pair',(),api_key='first-key'),store.settings);headers=[]
    async def handler(request):
        headers.append(request.headers['Authorization'])
        body=json.loads(request.content);wire=json.loads(body['messages'][1]['content'])
        wire_payload={**payload(),'supporting_segment_ids':[wire['segments'][0]['id']]}
        return httpx.Response(200,content='data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(wire_payload)}}]})+'\n\ndata: [DONE]\n\n')
    provider.transport=httpx.MockTransport(handler)
    await provider.complete(context(),SuggestionPayload);client=provider._client
    provider.key='replacement-key'
    await provider.complete(context(),SuggestionPayload)
    assert provider._client is client and not client.is_closed
    assert headers==['Bearer first-key','Bearer replacement-key']
    assert 'Authorization' not in client.headers
    assert [m['client_reused'] for m in provider.metrics]==[False,True]
    await provider.aclose()
    assert client.is_closed and provider._client is None

@pytest.mark.acceptance('AI-04','AI-07','OPS-03')
def test_live_prompt_projection_keeps_evidence_and_discards_irrelevant_metadata():
    snapshot=dict(transcript_revision=7,meeting_id='internal-meeting',input_hash='internal-hash',index_generation={'src':9},self_speaker='Minh',action='suggest',question='Which status?',sentence_limit=2,
        segments=[dict(id='s',speaker='Alex',text='NOT deploy Friday; 15 seconds.',capture_epoch='internal-epoch',revision=2)],
        memory=[dict(id='m',speaker='Minh',text='I will check staging.')],
        sources=[dict(id='chunk',source_id='parent',project_id='internal-project',content='HTTP 401 conflicts with ticket 403.',title='API-17',stale=True,indexed_at='2026-10-17',kind='text',generation=9)],
        glossary={'API-17':'auth'},validation_feedback={'code':'AI_CITATION'})
    wire=live_context(snapshot)
    assert wire['segments']==[dict(id='T1',speaker='Alex',text='NOT deploy Friday; 15 seconds.')]
    assert wire['memory'][0]['text']=='I will check staging.'
    assert wire['sources'][0]['content']==snapshot['sources'][0]['content'] and wire['sources'][0]['stale']
    assert wire['output_constraints']==dict(input_revision=7,allowed_source_ids=['C1'],allowed_supporting_segment_ids=['T1','T2'])
    assert wire['focus_segment_id']=='T1'
    assert wire['glossary']==snapshot['glossary'] and wire['validation_feedback']==snapshot['validation_feedback']
    assert 'source_id' not in wire['sources'][0] and 'meeting_id' not in wire and 'input_hash' not in wire
    assert snapshot['sources'][0]['source_id']=='parent'  # Original audit/citation snapshot is intact.

@pytest.mark.acceptance('AI-04','AI-08','OPS-03')
async def test_live_aliases_expand_only_within_request_and_reject_unknown_ids(tmp_path,store):
    original=dict(transcript_revision=1,segments=[dict(id=uid(),speaker='Alex',text='What is the status?')],
        memory=[dict(id=uid(),speaker='Minh',text='The deadline is unconfirmed.')],
        sources=[dict(id=uid(),source_id='parent-1',content='HTTP 401.'),dict(id=uid(),source_id='parent-2',content='HTTP 403.')])
    provider=Provider(Config(tmp_path,'pair',(),api_key='fake'),store.settings);calls=[]
    async def handler(request):
        body=json.loads(request.content);wire=json.loads(body['messages'][1]['content']);calls.append(wire)
        assert wire['output_constraints']['allowed_source_ids']==['C1','C2']
        assert wire['segments'][0]['id']=='T1' and wire['memory'][0]['id']=='T2'
        response={**payload(),'findings':[dict(text_vi='Nguồn thứ hai ghi 403.',source_ids=['C2'])],
            'evidence_status':'partial','supporting_segment_ids':['T2']}
        if len(calls)==1:response['findings'][0]['source_ids']=['parent-2']
        if len(calls)==2:response['supporting_segment_ids']=['T404']
        return httpx.Response(200,content='data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(response)}}]})+'\n\ndata: [DONE]\n\n')
    provider.transport=httpx.MockTransport(handler)
    for code in ('AI_CITATION','AI_EVIDENCE'):
        with pytest.raises(AppError) as error:await provider.complete(original,SuggestionPayload)
        assert error.value.code==code
    output=await provider.complete(original,SuggestionPayload)
    assert output.findings[0].source_ids==[original['sources'][1]['id']]
    assert output.supporting_segment_ids==[original['memory'][0]['id']]
    validate_suggestion(output,original)
    changed={**original,'sources':[{**s,'id':uid()} for s in original['sources']]}
    output=await provider.complete(changed,SuggestionPayload)
    assert output.findings[0].source_ids==[changed['sources'][1]['id']]
    assert output.findings[0].source_ids!=[original['sources'][1]['id']]
    await provider.aclose()

@pytest.mark.acceptance('AI-09','OPS-01')
async def test_cancelled_stream_closes_response_and_pool_can_serve_next_request(tmp_path,store):
    entered=asyncio.Event();closed=asyncio.Event();calls=[]
    class HangingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            entered.set()
            yield b'data: {"choices":[{"delta":{"content":"{"}}]}\n\n'
            await asyncio.Event().wait()
        async def aclose(self):closed.set()
    async def handler(request):
        calls.append(1)
        if len(calls)==1:return httpx.Response(200,stream=HangingStream())
        response={**payload(),'supporting_segment_ids':['T1']}
        return httpx.Response(200,content='data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(response)}}]})+'\n\ndata: [DONE]\n\n')
    provider=Provider(Config(tmp_path,'pair',(),api_key='fake'),store.settings);provider.transport=httpx.MockTransport(handler)
    task=asyncio.create_task(provider.complete(context(),SuggestionPayload));await entered.wait();client=provider._client;task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert closed.is_set() and not client.is_closed
    result=await provider.complete(context(),SuggestionPayload)
    validate_suggestion(result,context())
    assert provider._client is client and provider.metrics[0]['status']=='cancelled'
    await provider.aclose()

@pytest.mark.acceptance('OPS-01','AI-08')
async def test_semantic_repair_does_not_retry_provider_timeouts_or_bad_json(store):
    class FailedProvider:
        def __init__(self,code):self.code=code;self.calls=0
        async def complete(self,*args,**kwargs):self.calls+=1;raise AppError(self.code,'Controlled failure',502)
    for code in ('PROVIDER_TIMEOUT','PROVIDER_AUTH','AI_SCHEMA'):
        provider=FailedProvider(code);service=Service(store,None,provider)
        with pytest.raises(AppError) as error:await service.generate_suggestion(context())
        assert error.value.code==code and provider.calls==1

class SlowProvider:
    def __init__(self):self.started=[];self.waiters=[];self.cancelled=0
    async def complete(self,snapshot,schema,report=False):
        self.started.append(snapshot);future=asyncio.get_running_loop().create_future();self.waiters.append(future)
        try:await future
        except asyncio.CancelledError:self.cancelled+=1;raise
        return demo_suggestion(snapshot)

async def settle(predicate,timeout=2):
    until=asyncio.get_running_loop().time()+timeout
    while not predicate():
        if asyncio.get_running_loop().time()>until:raise AssertionError('Background condition did not complete')
        await asyncio.sleep(.005)

@pytest.mark.acceptance('AI-05','AI-09','UX-02')
async def test_one_active_latest_queued_stale_and_card_snapshot(store,meeting):
    provider=SlowProvider();service=Service(store,Retrieval(store,Semantic(Path('.'))),provider);id=meeting['id']
    store.apply_caption(id,caption(text='Question A'))
    a=service.schedule(id,dict(action='auto'));await settle(lambda:len(provider.waiters)==1)
    store.apply_caption(id,caption(text='Question B',segment='s2',seq=2))
    b=service.schedule(id,dict(action='auto'));c=service.schedule(id,dict(action='auto'))
    assert store.objects(id,'ai_requests')[1]['status']=='superseded'
    provider.waiters[0].set_result(True);await settle(lambda:len(provider.waiters)==2)
    assert store.objects(id,'suggestions')[0]['stale']
    provider.waiters[1].set_result(True);await settle(lambda:len(store.objects(id,'suggestions'))==2)
    assert not store.objects(id,'suggestions')[-1]['stale']
    card=store.objects(id,'suggestions')[0]
    d=service.schedule(id,dict(action='shorter',base_suggestion_id=card['id']))
    await settle(lambda:len(provider.waiters)==3)
    assert provider.started[-1]['segments'][0]['text']=='Question A'
    assert len(provider.started[-1]['segments'])==1
    provider.waiters[-1].set_result(True);await settle(lambda:len(store.objects(id,'suggestions'))==3)
    await service.shutdown()

@pytest.mark.acceptance('AI-09')
async def test_immediate_manual_cancellation_and_auto_quota_still_allow_manual(store,meeting):
    provider=SlowProvider();service=Service(store,Retrieval(store,Semantic(Path('.'))),provider);id=meeting['id'];store.apply_caption(id,caption())
    service.schedule(id,dict(action='auto'))
    # Cancel the runner before its first event-loop turn: it must still launch the latest manual job.
    latest=service.schedule(id,dict(action='suggest'))
    assert service.schedule(id,dict(action='auto'))==latest
    await settle(lambda:len(provider.waiters)==1)
    assert provider.started[0]['action']=='suggest'
    store.set_settings({'auto_per_minute':1});service.rate[id].append(__import__('time').monotonic())
    with pytest.raises(AppError) as e:service.schedule(id,dict(action='auto'))
    assert e.value.code=='AUTO_QUOTA'
    manual=service.schedule(id,dict(action='suggest'));await settle(lambda:provider.cancelled==1)
    await settle(lambda:len(provider.waiters)==2)
    provider.waiters[-1].set_result(True);await settle(lambda:any(s['request_id']==manual for s in store.objects(id,'suggestions')))
    await service.shutdown()

@pytest.mark.acceptance('AI-05','AI-09')
async def test_snapshot_cache_is_scoped_and_confirmed_memory_invalidation(store,meeting):
    from datetime import datetime,timezone,timedelta
    from app.storage import dumps
    service=Service(store,Retrieval(store,Semantic(Path('.'))),SlowProvider());id=meeting['id']
    older=caption(text='Confirmed: staging first.',segment='older');older['observed_at']=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat();store.apply_caption(id,older)
    m=store.meeting(id);m['confirmed_segment_ids']=['older']
    with store.disk:store.save_meeting(store.disk,m)
    store.apply_caption(id,caption(text='What is next?',segment='new',seq=2))
    prepared=service.prepare(id,dict(action='suggest'))
    assert [s['id'] for s in prepared['segments']]==['new']
    assert prepared['memory'][0]['id']=='older'
    service.provider.complete=lambda *a,**k:None
    # Use the labeled deterministic demo provider to verify cache orchestration only.
    m=store.meeting(id);m['demo']=True
    with store.disk:store.save_meeting(store.disk,m)
    first=service.schedule(id,dict(action='suggest'));await settle(lambda:len(store.objects(id,'suggestions'))==1)
    assert service.schedule(id,dict(action='suggest'))==first
    assert len(store.objects(id,'ai_requests'))==1
    store.set_settings({'model':'other-model'})
    assert service.schedule(id,dict(action='suggest'))!=first
    await settle(lambda:len(store.objects(id,'suggestions'))==2)
    change=caption(text='Confirmed: production first.',segment='older',revision=2,seq=3);store.apply_caption(id,change)
    assert store.meeting(id)['confirmed_segment_ids']==[]
    assert store.meeting(id)['memory_revision_warnings']==1
    assert store.objects(id,'suggestions')[0]['stale']
    await service.shutdown()

@pytest.mark.acceptance('REP-01')
def test_long_report_chunks_cover_every_turn_and_tail(store):
    service=Service(store,None,None)
    segments=[{'id':str(n),'text':f'Turn {n}: '+('long text '*200)} for n in range(80)]
    segments.append({'id':'tail','text':'TAIL REQUIREMENT: preserve the billing audit log.'})
    parts=service.report_chunks(segments,budget=4000)
    covered={s['id'] for part in parts for s in part}
    assert covered=={s['id'] for s in segments}
    assert any('TAIL REQUIREMENT' in s['text'] for s in parts[-1])
    assert len(parts)>10

@pytest.mark.acceptance('RAG-04')
async def test_conflicting_ticket_and_code_are_both_in_request_with_valid_citations(store,meeting):
    from app.ingestion import Ingestion
    id=meeting['id'];p=meeting['project_id']
    for title,kind,text in [('Ticket API-17','text','API-17 requires HTTP 403 on expired token.'),('Source auth.ts','text','API-17 local code snapshot returns HTTP 401. This is not deployment evidence.')]:
        source=Ingestion(store).add(p,dict(kind=kind,title=title,pasted_text=text));assert Ingestion(store).sync(source['id'])['status']=='ready'
    store.apply_caption(id,caption(text='What does API-17 return on an expired token?'))
    class ConflictProvider:
        async def complete(self,snapshot,schema,report=False):
            assert {s['title'] for s in snapshot['sources']}=={'Ticket API-17','Source auth.ts'}
            return SuggestionPayload(input_revision=snapshot['transcript_revision'],intent='question',meaning_vi='Ticket và code snapshot đang khác nhau.',findings=[dict(text_vi=s['content'],source_ids=[s['id']]) for s in snapshot['sources']],reply_en='The ticket and the code show different results. Which behavior is approved?',reply_vi='Ticket và code có kết quả khác nhau. Hành vi nào được duyệt?',clarification_en='Which behavior is approved?',evidence_status='conflicting',uncertainties=['Code local không chứng minh production.'],supporting_segment_ids=[snapshot['segments'][-1]['id']])
    service=Service(store,Retrieval(store,Semantic(Path('.'))),ConflictProvider());service.schedule(id,dict(action='suggest'));await settle(lambda:bool(store.objects(id,'suggestions')))
    assert store.objects(id,'suggestions')[0]['payload']['evidence_status']=='conflicting'
    await service.shutdown()

@pytest.mark.acceptance('REP-01')
async def test_report_pipeline_calls_every_map_and_retains_start_and_tail_evidence(store,meeting):
    id=meeting['id']
    texts=['START_REQUIREMENT: preserve audit records.']+[f'Observed turn {n}: '+('details '*300) for n in range(30)]+['TAIL_REQUIREMENT: support nullable status.']
    for n,text in enumerate(texts):store.apply_caption(id,caption(text=text,segment=str(n),seq=n+1))
    store.control(id,dict(action='end',idempotency_key=uid()))
    class MapProvider:
        calls=[]
        async def complete(self,context,schema,report=False):
            self.calls.append([s['id'] for s in context['segments']])
            return ReportPayload(summary_vi='Phần phụ đề đã quan sát.',summary_segment_ids=[context['segments'][0]['id']],requirements=[dict(id='model-local-r1',text=s['text'],evidence_segment_ids=[s['id']],origin='transcript') for s in context['segments'] if 'REQUIREMENT:' in s['text']])
    provider=MapProvider();service=Service(store,None,provider);job=service.report(id,store.meeting(id)['transcript_revision']);await settle(lambda:job['status'] in ('ready','error'))
    assert job['status']=='ready',job
    report=service.get_report(job['report_id']);items=report['payload']['requirements']
    assert any('START_REQUIREMENT' in i['text'] for i in items) and any('TAIL_REQUIREMENT' in i['text'] for i in items)
    assert len({i['id'] for i in items})==len(items)
    assert len(provider.calls)>1 and {id for group in provider.calls for id in group}==set(map(str,range(len(texts))))
    await service.shutdown()

@pytest.mark.acceptance('AI-02','AI-08','REP-03')
async def test_report_correction_is_bounded_and_rejected_draft_never_published(store,meeting):
    id=meeting['id'];store.apply_caption(id,caption(text='Maybe Friday, but no deadline is confirmed.'))
    store.control(id,dict(action='end',idempotency_key=uid()))
    class RepairProvider:
        def __init__(self,repair):self.calls=[];self.repair=repair
        async def complete(self,context,schema,report=False):
            self.calls.append(context)
            assert not store.objects(id,'reports')
            item=dict(id='q',text='Thứ Sáu chưa được xác nhận.',evidence_segment_ids=['seg-1'],origin='transcript',confirmation='unconfirmed',raw_due_text='Friday')
            # The source ID comes from the actual caption fixture, not a guessed ID.
            item['evidence_segment_ids']=[context['segments'][0]['id']]
            if len(self.calls)==2:
                assert context['segments']==self.calls[0]['segments']
                assert context['validation_feedback']['issues'][0]['code']=='REPORT_DUE'
                if self.repair:item['raw_due_text']=None
            return ReportPayload(open_questions=[item])
    for repairs in (False,True):
        provider=RepairProvider(repairs);service=Service(store,None,provider)
        job=service.report(id,store.meeting(id)['transcript_revision']);await settle(lambda:job['status'] in ('ready','error'))
        assert len(provider.calls)==2
        assert job['status']==('ready' if repairs else 'error'),job
        assert len(store.objects(id,'reports'))==(1 if repairs else 0)
        if repairs:assert service.get_report(job['report_id'])['payload']['open_questions'][0]['raw_due_text'] is None
        await service.shutdown()

@pytest.mark.acceptance('AI-04','AI-08')
async def test_suggestion_citation_correction_preserves_snapshot_and_stops_after_two_attempts(store):
    class CitationProvider:
        def __init__(self,repair):self.calls=[];self.repair=repair
        async def complete(self,snapshot,schema,report=False):
            self.calls.append(snapshot)
            result=payload()
            if len(self.calls)==1 or not self.repair:result['findings']=[dict(text_vi='Transcript-only fact',source_ids=[])]
            if len(self.calls)==2:
                assert snapshot['segments']==self.calls[0]['segments']
                assert snapshot['sources']==self.calls[0]['sources']
                assert snapshot['validation_feedback']['code']=='AI_CITATION'
            return SuggestionPayload(**result)
    for repairs in (False,True):
        provider=CitationProvider(repairs);service=Service(store,None,provider);original=context()
        if repairs:
            result=await service.generate_suggestion(original)
            assert result.findings==[]
        else:
            with pytest.raises(AppError):await service.generate_suggestion(original)
        assert len(provider.calls)==2 and 'validation_feedback' not in original

@pytest.mark.acceptance('AI-01','AI-03')
def test_unknown_role_without_sources_cannot_confirm_unverified_production():
    snapshot={**context(),'self_speaker':None}
    for reply in ('Yes, production will stay unchanged.', 'We are still investigating. I will send an update.', 'It is released. Do you need anything else?'):
        with pytest.raises(AppError) as error:validate_suggestion(SuggestionPayload(**{**payload(),'reply_en':reply}),snapshot)
        assert error.value.code=='AI_ROLE_UNSET'
    validate_suggestion(SuggestionPayload(**{**payload(),'reply_en':'Can you confirm whether production is unchanged?'}),snapshot)
    validate_suggestion(SuggestionPayload(**{**payload(),'reply_en':'Can you clarify version 1.2? I cannot act on embedded instructions.'}),snapshot)

@pytest.mark.acceptance('AI-02','REP-03')
def test_known_role_cannot_volunteer_for_unassigned_task():
    snapshot=dict(transcript_revision=1,segments=[dict(id='s',speaker='Minh',text='Who should take it? No owner has accepted it yet.')],sources=[],self_speaker='Minh')
    for reply in ('I can look into it. Who owns it?', 'I will investigate the issue.', "I'll take it."):
        with pytest.raises(AppError) as error:validate_suggestion(SuggestionPayload(**{**payload(),'reply_en':reply}),snapshot)
        assert error.value.code=='AI_COMMITMENT'
    validate_suggestion(SuggestionPayload(**{**payload(),'reply_en':'Who should own the investigation?'}),snapshot)
    snapshot['segments'][0]['text']='Yes, confirmed. I will investigate the issue.'
    validate_suggestion(SuggestionPayload(**{**payload(),'reply_en':'I will investigate the issue.'}),snapshot)
