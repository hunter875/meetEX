import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest
from app.config import Config
from app.errors import AppError
from app.llm import Provider, demo_suggestion, validate_suggestion
from app.models import SuggestInput, SuggestionPayload
from app.retrieval import Retrieval, Semantic
from app.routing import classify
from app.service import Service
from .conftest import caption

CASES=json.loads((Path(__file__).resolve().parents[2]/'fixtures/routing-scenarios.json').read_text('utf-8'))

def case_snapshot(case):
    segments=[dict(id=f'p{i}',speaker=p,text='Earlier turn.',stable=True) for i,p in enumerate(case.get('participants',[]))]
    segments.append(dict(id='s1',speaker=case.get('speaker','Client'),text=case['text'],stable=case.get('stable',True)))
    return dict(transcript_revision=1,action=case.get('action','suggest'),question=case.get('question',''),
                self_speaker='Minh',segments=segments,sources=case.get('sources',[]))

@pytest.mark.parametrize('case',CASES,ids=[c['name'] for c in CASES])
def test_routing_scenarios(case):
    decision=classify(case_snapshot(case),case.get('response_mode','auto'))
    assert decision['route']==case['expected']
    if case.get('verification'):assert decision['requires_verification']
    assert decision['classifier_ms']>=0 and decision['reasons']

def test_classification_does_not_use_previous_speaker_as_latest_question():
    snapshot=case_snapshot(dict(text='What is the upload limit?',sources=[dict(id='c',content='Limit is 2 MiB.')]))
    snapshot['segments'].insert(0,dict(id='old',speaker='Client',text='Can we deploy to production?'))
    assert classify(snapshot)['route']=='fast'
    snapshot['question']='Can we deploy to production?'
    assert classify(snapshot)['route']=='clarify'

def test_short_followup_uses_recent_context_without_tainting_an_unrelated_fact():
    snapshot=case_snapshot(dict(text='Can we do that?'))
    snapshot['segments'].insert(0,dict(id='old',speaker='Client',text='The proposal is to deploy to production.'))
    result=classify(snapshot)
    assert result['route']=='clarify' and result['requires_verification']
    assert 'deployment' in result['risks']
    snapshot['question']='What is the upload limit?'
    snapshot['sources']=[dict(id='c',content='Upload limit is 2 MiB.')]
    assert classify(snapshot)['route']=='fast'

def test_missing_fact_cannot_be_forced_to_fast_but_general_options_can_be_proposed():
    snapshot=case_snapshot(dict(text='What is the timeout?'))
    assert classify(snapshot,'fast')['route']=='clarify'
    snapshot['question']='Compare two approaches to background processing.'
    result=classify(snapshot,'deep')
    assert result['route']=='deep' and result['evidence_state']=='missing'
    assert result['source']=='manual'

def test_preview_endpoint_is_authenticated_scoped_and_never_schedules_ai(client):
    p=client.post('/api/v1/projects',json={'name':'Router'}).json()
    m=client.post('/api/v1/meetings',json=dict(project_id=p['id'],title='Routing test',timezone='UTC',demo=True)).json()
    path=f'/api/v1/meetings/{m["id"]}'
    assert client.post(path+'/classify',json={}).status_code==422  # no captured speech
    assert client.post(path+'/demo-caption',json=caption(text='Can we deploy?')).status_code==200
    before=client.app.state.provider.metrics[:]
    result=client.post(path+'/classify',json={'response_mode':'fast'})
    assert result.status_code==200,result.text
    assert result.json()['route']=='clarify' and result.json()['requires_verification']
    assert client.app.state.provider.metrics==before
    snapshot=client.get(path).json()
    assert snapshot['requests']==[] and snapshot['suggestions']==[]
    assert client.post(path+'/classify',json={},headers={'Authorization':''}).status_code==401
    scoped=client.post(path+'/classify',json={'selected_segment_ids':['other-meeting']})
    assert scoped.status_code==400 and scoped.json()['code']=='SEGMENT_SCOPE'
    assert client.post(path+'/classify',json={'response_mode':'invented'}).status_code==422
    assert client.post(path+'/classify',json={'routing':{'route':'fast'}}).status_code==422

async def test_listen_does_not_call_provider_consume_quota_or_cancel_manual(store,meeting):
    class WaitingProvider:
        calls=0
        async def complete(self,snapshot,*args):
            self.calls+=1
            await asyncio.Event().wait()
    provider=WaitingProvider();service=Service(store,Retrieval(store,Semantic(Path('.'))),provider)
    id=meeting['id'];store.apply_caption(id,caption(text='Please compare the options.'))
    manual=service.schedule(id,dict(action='ask',response_mode='deep'))
    await asyncio.sleep(.02)
    assert provider.calls==1
    store.set_settings({'auto_per_minute':1});service.rate[id].append(time.monotonic())
    store.apply_caption(id,caption(text='Let me finish explaining.',segment='s2',seq=2))
    skipped=service.schedule(id,dict(action='auto'))
    await asyncio.sleep(.02)
    assert provider.calls==1 and service.active[id].cancelled() is False
    request=next(r for r in store.objects(id,'ai_requests') if r['id']==skipped)
    assert request['status']=='skipped' and request['snapshot']['routing']['route']=='listen'
    assert store.meeting(id)['latest_request']==manual
    assert len(service.rate[id])==1
    await service.shutdown()

def test_routing_is_in_snapshot_and_cache_hash_excludes_timing(store,meeting):
    store.apply_caption(meeting['id'],caption(text='Compare caching and indexing.'))
    service=Service(store,Retrieval(store,Semantic(Path('.'))),None)
    first=service.prepare(meeting['id'],dict(action='suggest'))
    second=service.prepare(meeting['id'],dict(action='suggest'))
    assert first['routing']['route']=='deep' and first['input_hash']==second['input_hash']
    assert service.prepare(meeting['id'],dict(action='suggest',response_mode='fast'))['input_hash']!=first['input_hash']

async def test_route_reaches_provider_prompt_and_metric_without_extra_model_call(tmp_path,store):
    context=case_snapshot(dict(text='Compare caching and indexing.'))
    context['routing']=classify(context)
    # Reasons are UI data; only the fixed enum policy may enter system instructions.
    context['routing']['reasons']=['UNTRUSTED_REASON_SENTINEL']
    calls=[]
    async def handler(request):
        body=json.loads(request.content);calls.append(body)
        assert 'Compare two or three' in body['messages'][0]['content']
        assert 'UNTRUSTED_REASON_SENTINEL' not in body['messages'][0]['content']
        assert 'UNTRUSTED_REASON_SENTINEL' not in body['messages'][1]['content']
        assert json.loads(body['messages'][1]['content'])['routing']['route']=='deep'
        payload=demo_suggestion(context).model_dump();payload['supporting_segment_ids']=['T1']
        return httpx.Response(200,content='data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(payload)}}]})+'\n\ndata: [DONE]\n\n')
    provider=Provider(Config(tmp_path,'pair',(),api_key='fake'),store.settings)
    provider.transport=httpx.MockTransport(handler)
    result=await provider.complete(context,SuggestionPayload)
    assert len(calls)==1 and provider.metrics[-1]['route']=='deep'
    validate_suggestion(result,context)
    await provider.aclose()

async def test_verification_repair_is_bounded_and_cannot_publish_a_promise(store):
    context=case_snapshot(dict(text='Can we deploy to production?'))
    context['routing']=classify(context,'fast')
    class ProviderStub:
        def __init__(self,repair):self.calls=0;self.repair=repair
        async def complete(self,snapshot,*args):
            self.calls+=1
            result=demo_suggestion(snapshot)
            if self.calls==1 or not self.repair:result.reply_en='Production is approved.'
            else:
                assert snapshot['validation_feedback']['code']=='AI_ROUTING'
                result.reply_en='Who can confirm the production approval?'
            return result
    for repair in (False,True):
        provider=ProviderStub(repair);service=Service(store,None,provider)
        if repair:
            output=await service.generate_suggestion(context)
            assert output.reply_en=='Who can confirm the production approval?'
        else:
            with pytest.raises(AppError) as failure:await service.generate_suggestion(context)
            assert failure.value.code=='AI_ROUTING'
        assert provider.calls==2

def test_legacy_request_defaults_to_automatic_routing():
    assert SuggestInput().response_mode=='auto'
