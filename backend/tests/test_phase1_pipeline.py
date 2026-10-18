"""HTTP -> actual Provider SSE adapter -> guards/repair -> storage/events. No network."""
import copy
import json
import time

import httpx
import pytest
from app.models import ReportPayload, ReportEdit
from app.service import Service
from app.storage import uid
from .conftest import caption
from .test_api import until


def real_meeting(client, speech):
    project=client.post('/api/v1/projects',json={'name':'Phase 1 pipeline'}).json()
    response=client.post('/api/v1/meetings',json=dict(project_id=project['id'],title='Controlled provider pipeline',demo=False))
    assert response.status_code==201
    meeting=response.json()
    store=client.app.state.store
    for n,(speaker,text) in enumerate(speech):
        event=caption(text=text,segment=f's{n}',seq=n+1)
        event['speaker_label']=speaker
        store.apply_caption(meeting['id'],event)
    assert client.put('/api/v1/provider/credential',json={'api_key':'FAKE_PHASE1_TEST_KEY'}).status_code==200
    return project,meeting


def capture_events(service):
    events=[]
    async def observe(event):
        events.append(copy.deepcopy(event))
    service.listeners.add(observe)
    return events


def sse(payload):
    return httpx.Response(200,content='data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(payload)}}]})+'\n\ndata: [DONE]\n\n')


@pytest.mark.parametrize('mode',['fast','explain','deep','clarify'])
@pytest.mark.parametrize('repair',[False,True])
@pytest.mark.parametrize('kind',['numeric','task'])
def test_suggestion_guards_repair_and_publication_through_http(client,mode,repair,kind):
    speech=[('Minh','I will review the CSV formatting.'),('Alex','Please restate the accepted work.')]
    if kind=='numeric':speech=[('Alex','What is the approved timeout?')]
    project,meeting=real_meeting(client,speech)
    id=meeting['id']
    if kind=='numeric':
        imported=client.post(f'/api/v1/projects/{project["id"]}/sources',json=dict(kind='text',title='Timeout setting',pasted_text='Approved timeout is 15 seconds.'))
        assert imported.status_code==201,imported.text
    else:
        assert client.patch(f'/api/v1/meetings/{id}',json={'self_speaker':'Minh'}).status_code==200
    events=capture_events(client.app.state.service)
    requests=[]
    async def handler(request):
        wire=json.loads(json.loads(request.content)['messages'][1]['content'])
        requests.append(wire)
        if len(requests)>1:
            for field in ('segments','sources','memory','transcript_revision'):
                assert wire[field]==requests[0][field]
            assert 'validation_feedback' in wire
            assert client.app.state.store.objects(id,'suggestions')==[]
        valid=repair and len(requests)==2
        payload=dict(input_revision=wire['transcript_revision'],intent='update',meaning_vi='Đối chiếu yêu cầu.',findings=[],
                     reply_en='Could you clarify?',reply_vi='Bạn làm rõ giúp nhé?',clarification_en='',
                     evidence_status='missing',uncertainties=[],supporting_segment_ids=[s['id'] for s in wire['segments']])
        if kind=='numeric':
            value=15 if valid else 90
            payload.update(findings=[dict(text_vi=f'Approved timeout is {value} seconds.',source_ids=[wire['sources'][0]['id']])],evidence_status='supported',
                           reply_en=f'The approved timeout is {value} seconds.',reply_vi=f'Thời gian chờ được duyệt là {value} giây.')
        else:
            payload['reply_en']='I will review the CSV formatting.' if valid else 'I will rewrite the authentication service.'
        if valid and mode=='clarify':payload['reply_en']='Can you confirm these details?'
        return sse(payload)
    client.app.state.provider.transport=httpx.MockTransport(handler)
    response=client.post(f'/api/v1/meetings/{id}/suggest',json={'response_mode':mode})
    assert response.status_code==202
    snapshot=until(client,f'/api/v1/meetings/{id}',lambda s:s['requests'][-1]['status'] in ('ready','error'))
    assert len(requests)==2
    assert snapshot['requests'][-1]['snapshot']['routing']['route']==mode
    ready=[event for event in events if event['type']=='suggestion.ready']
    if repair:
        assert snapshot['requests'][-1]['status']=='ready' and len(snapshot['suggestions'])==len(ready)==1, snapshot['requests'][-1]
        serialized=json.dumps(ready)
        assert ('90 seconds' if kind=='numeric' else 'rewrite the authentication') not in serialized
    else:
        assert snapshot['requests'][-1]['status']=='error' and snapshot['suggestions']==[] and ready==[]
        assert snapshot['requests'][-1]['error']['code']==('AI_NUMERIC' if kind=='numeric' else 'AI_COMMITMENT')
    assert all(not s['mode']=='demo' for s in snapshot['suggestions'])


@pytest.mark.parametrize('repair',[False,True])
@pytest.mark.parametrize('wrong_field',['summary','item'])
def test_report_repair_preserves_user_version_and_only_publishes_valid_report(client,repair,wrong_field):
    _,meeting=real_meeting(client,[('Alex','Confirmed: test in staging only. Production approval is still pending.')])
    id=meeting['id']
    assert client.post(f'/api/v1/meetings/{id}/control',json={'action':'end','idempotency_key':'end'}).status_code==200
    service=client.app.state.service
    segments=client.app.state.store.transcript(id)
    valid=ReportPayload(summary_en='Test in staging only.',summary_segment_ids=[s['id'] for s in segments],
                        decisions=[dict(id='d',text='Test in staging only.',evidence_segment_ids=[s['id'] for s in segments],origin='transcript',confirmation='confirmed')])
    initial=service.save_report(id,valid,1)
    edit=copy.deepcopy(initial['payload']);edit['summary_vi']='USER_EDIT_PRESERVED'
    saved=client.patch('/api/v1/reports/'+initial['id'],json={'expected_version':1,'payload':edit,'reviewed':True}).json()
    assert saved['version']==2
    before=copy.deepcopy(saved)
    events=capture_events(service)
    requests=[]
    async def handler(request):
        wire=json.loads(json.loads(request.content)['messages'][1]['content'])
        requests.append(wire)
        if len(requests)==2:
            assert wire['segments']==requests[0]['segments']
            assert 'validation_feedback' in wire
            assert len(client.app.state.store.objects(id,'reports'))==2
        payload=valid.model_dump()
        if len(requests)==1 or not repair:
            if wrong_field=='summary':payload['summary_en']='Production deployment is approved.'
            else:payload['decisions'][0]['text_en']='Production deployment is approved.'
        return sse(payload)
    client.app.state.provider.transport=httpx.MockTransport(handler)
    revision=client.get(f'/api/v1/meetings/{id}').json()['transcript_revision']
    response=client.post(f'/api/v1/meetings/{id}/reports',json={'transcript_revision':revision})
    assert response.status_code==202,response.text
    job=until(client,'/api/v1/jobs/'+response.json()['id'],lambda j:j['status'] in ('ready','error'))
    assert len(requests)==2
    ready=[event for event in events if event['type']=='report.ready']
    assert len(ready)==(1 if repair else 0)
    assert 'Production deployment is approved.' not in json.dumps(ready)
    assert job['status']==('ready' if repair else 'error')
    if not repair:assert job['error']['code']=='REPORT_CLAIM'
    assert client.get('/api/v1/reports/'+saved['id']).json()==before
    assert client.get('/api/v1/reports/'+saved['id']+'/export?format=json').json()==before
    assert len(client.app.state.store.objects(id,'reports'))==(3 if repair else 2)


async def test_final_merge_is_validated_before_save(store, meeting, monkeypatch):
    text = 'Confirmed: deploy to production if staging passes.'
    event = caption(text=text)
    store.apply_caption(meeting['id'], event)
    store.control(meeting['id'], dict(action='end', idempotency_key=uid()))
    original_segment = store.transcript(meeting['id'])[0]
    split = text.index('if staging')
    parts = [[{**original_segment, 'text': text[:split]}],
             [{**original_segment, 'text': text[split:]}]]
    class MapProvider:
        def __init__(self): self.calls = 0
        async def complete(self, context, *args):
            self.calls += 1
            if self.calls == 1:
                return ReportPayload(decisions=[dict(id='d', text='Deploy to production.',
                    evidence_segment_ids=[original_segment['id']], origin='transcript', confirmation='confirmed')])
            return ReportPayload()
    provider = MapProvider()
    service = Service(store, None, provider)
    old = service.save_report(meeting['id'], ReportPayload(summary_vi='USER_VERSION'), 1, user_edits=True)
    # Simulate a split oversized turn: each map is locally valid, but the original
    # complete turn carries a condition missing from map 1. No validator is mocked.
    monkeypatch.setattr(service, 'report_chunks', lambda segments: parts)
    events = capture_events(service)
    job = service.report(meeting['id'], store.meeting(meeting['id'])['transcript_revision'])
    import asyncio
    deadline = time.monotonic() + 3
    while job['status'] not in ('ready', 'error'):
        assert time.monotonic() < deadline
        await asyncio.sleep(.005)
    assert provider.calls == 2
    assert job['status'] == 'error' and job['error']['code'] == 'REPORT_CLAIM'
    assert store.objects(meeting['id'], 'reports') == [old]
    assert not any(event['type'] == 'report.ready' for event in events)
    await service.shutdown()


@pytest.mark.parametrize('change', ['caption', 'source'])
def test_repaired_result_uses_original_evidence_and_becomes_stale(client, change):
    from app.ingestion import Ingestion
    project, meeting = real_meeting(client, [('Alex', 'What is the approved timeout?')])
    id = meeting['id']
    imported = client.post(f'/api/v1/projects/{project["id"]}/sources', json=dict(
        kind='text', title='Timeout', pasted_text='Approved timeout is 15 seconds.')).json()
    store = client.app.state.store
    events = capture_events(client.app.state.service)
    wires = []
    async def handler(request):
        wire = json.loads(json.loads(request.content)['messages'][1]['content'])
        wires.append(wire)
        valid = len(wires) == 2
        if valid:
            assert wire['sources'] == wires[0]['sources']
            assert wire['segments'] == wires[0]['segments']
            if change == 'caption':
                store.apply_caption(id, caption(text='Please recheck a different setting.', revision=2, segment='s0', seq=2))
            else:
                source = store.source(imported['source_id'])
                source['config']['pasted_text'] = 'Approved timeout is 30 seconds.'
                with store.disk: store.save_source(source)
                assert Ingestion(store).sync(source['id'])['status'] == 'ready'
                client.app.state.service.source_changed(project['id'])
        value = 15 if valid else 90
        return sse(dict(input_revision=wire['transcript_revision'], intent='update', meaning_vi='Đối chiếu tham số.',
            findings=[dict(text_vi=f'Timeout is {value} seconds.', source_ids=[wire['sources'][0]['id']])],
            reply_en=f'The timeout is {value} seconds.', reply_vi='Bạn xem lại tham số nhé.', clarification_en='',
            evidence_status='supported', uncertainties=[], supporting_segment_ids=[wire['segments'][0]['id']]))
    client.app.state.provider.transport = httpx.MockTransport(handler)
    client.post(f'/api/v1/meetings/{id}/suggest', json={'response_mode':'fast'})
    result = until(client, f'/api/v1/meetings/{id}', lambda s:s['requests'][-1]['status'] in ('stale','error'))
    assert len(wires) == 2 and result['requests'][-1]['status'] == 'stale'
    assert result['suggestions'][-1]['stale']
    assert not any(event['type'] == 'suggestion.ready' for event in events)
    assert len([event for event in events if event['type'] == 'suggestion.stale']) == 1


async def test_old_validator_cache_cannot_republish_an_unrelated_promise(store,meeting):
    import asyncio
    import hashlib
    from app.retrieval import Retrieval, Semantic
    from pathlib import Path
    from app.storage import dumps
    event=caption(text='I will review the CSV formatting.')
    event['speaker_label']='Minh'
    store.apply_caption(meeting['id'],event)
    m=store.meeting(meeting['id']);m.update(self_speaker='Minh',demo=True)
    with store.disk:store.save_meeting(store.disk,m)
    service=Service(store,Retrieval(store,Semantic(Path('.'))),None)
    snapshot=service.prepare(meeting['id'],dict(action='suggest'))
    old_input={k:v for k,v in snapshot.items() if k!='input_hash'}
    old_input['routing']={k:v for k,v in old_input['routing'].items() if k!='classifier_ms'}
    legacy_hash=hashlib.sha256(dumps(old_input).encode()).hexdigest()
    assert legacy_hash!=snapshot['input_hash']
    legacy_snapshot={**snapshot,'input_hash':legacy_hash}
    request_id=uid()
    service.save_request(meeting['id'],dict(id=request_id,action='suggest',status='ready',snapshot=legacy_snapshot))
    legacy=dict(id=uid(),request_id=request_id,payload={'reply_en':'I will rewrite the authentication service.'},
                snapshot=legacy_snapshot,stale=False)
    with store.disk:
        store.disk.execute('INSERT INTO suggestions VALUES(?,?,?,?)',(legacy['id'],meeting['id'],request_id,dumps(legacy)))
    events=capture_events(service)
    new_request=service.schedule(meeting['id'],dict(action='suggest'))
    assert new_request!=request_id
    deadline=time.monotonic()+3
    while len(store.objects(meeting['id'],'suggestions'))<2:
        assert time.monotonic()<deadline
        await asyncio.sleep(.005)
    assert store.objects(meeting['id'],'suggestions')[0]==legacy
    assert 'rewrite the authentication' not in json.dumps(events)
    await service.shutdown()
