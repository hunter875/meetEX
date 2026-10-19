import asyncio
import json
import httpx
from app.storage import uid
from app.models import ReportPayload
from .test_phase1_pipeline import real_meeting,sse
from .test_api import until
from .test_phase4_memory import apply

def test_actual_report_provider_counts_retry_and_repair(client):
    _,meeting=real_meeting(client,[('Client','Confirmed: test API-17 in staging.')]);id=meeting['id'];calls=[]
    def handler(request):
        wire=json.loads(json.loads(request.content)['messages'][1]['content']);calls.append(wire)
        if len(calls)==1:return httpx.Response(503)
        good=ReportPayload(summary_en='Observed staging decision.',summary_segment_ids=['s0'],decisions=[dict(id='one',text='Confirmed: test API-17 in staging.',text_en='Confirmed: test API-17 in staging.',evidence_segment_ids=['s0'],origin='transcript',confirmation='confirmed')]).model_dump()
        if len(calls)==2:good['summary_segment_ids']=['foreign']
        return sse(good)
    client.app.state.provider.transport=httpx.MockTransport(handler)
    assert client.post(f'/api/v1/meetings/{id}/control',json=dict(action='end',idempotency_key=uid())).status_code==200
    response=client.post(f'/api/v1/meetings/{id}/reports',json=dict(transcript_revision=1));job=until(client,'/api/v1/jobs/'+response.json()['id'],lambda j:j['status'] in ('ready','error'))
    assert job['status']=='ready',job
    assert (job['http_attempts'],job['transient_retry_attempts'],job['repair_attempts'],job['usage_unknown_attempts'])==(3,1,1,3)
    assert len(calls)==3 and 'validation_feedback' in calls[-1]
    assert client.app.state.provider.metrics[-1]['logical_request_id']==job['id']

async def test_deleted_meeting_cache_is_not_repopulated_by_inflight_lookup(store,meeting):
    from app.retrieval import Retrieval,Semantic
    from pathlib import Path
    import threading
    store.set_settings(dict(semantic_enabled=True));began=threading.Event();release=threading.Event()
    class Held:
        ready=True
        def query(self,text):began.set();release.wait(2);return [1.,0.]
    retrieval=Retrieval(store,Held());lookup=asyncio.create_task(retrieval.search_async(meeting['project_id'],'private meeting phrase API-17'))
    ready=await asyncio.to_thread(began.wait,1)
    if lookup.done():await lookup
    assert ready
    assert 'private meeting phrase' not in repr(list(retrieval._inflight))
    retrieval.forget_queries();store.delete_meeting(meeting['id']);release.set();await lookup
    assert not retrieval._cache and not retrieval._vectors
    await retrieval.aclose()

def test_local_restart_and_api_edit_snapshot_history(client):
    store=client.app.state.store;p=store.create_project(dict(name='persist',description='',glossary={}));m=store.create_meeting(dict(project_id=p['id'],title='Local',timezone='UTC',persistence_mode='local',demo=True));apply(store,m,'I will review API-17.')
    item=store.memory(m['id'])[0]
    response=client.patch(f'/api/v1/meetings/{m["id"]}/memory/{item["id"]}',json=dict(expected_version=1,owner='Alex',status='cancelled'))
    assert response.status_code==200 and response.json()['origin']=='user_edit'
    assert client.patch(f'/api/v1/meetings/{m["id"]}/memory/{item["id"]}',json=dict(expected_version=1,owner='Other')).status_code==409
    assert len(client.get(f'/api/v1/meetings/{m["id"]}/memory/{item["id"]}/history').json())==2
    from app.storage import Storage
    path=store.disk.execute('PRAGMA database_list').fetchone()['file'];second=Storage(__import__('pathlib').Path(path).parent)
    try:assert second.memory(m['id'])[0]['owner']=='Alex' and second.meeting(m['id'])['status']=='interrupted'
    finally:second.close()
