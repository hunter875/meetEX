import json
import time
import httpx
import pytest
from starlette.websockets import WebSocketDisconnect
from app.storage import uid
from .conftest import caption

ORIGIN='chrome-extension://'+'a'*32
WS_HEADERS={'Origin':ORIGIN,'Host':'127.0.0.1:8765'}
def project(client,name='Project'):return client.post('/api/v1/projects',json={'name':name}).json()
def meeting(client,p,demo=False,memory=False):
    result=client.post('/api/v1/meetings',json=dict(project_id=p['id'],title='API meeting',timezone='America/Los_Angeles',persistence_mode='memory' if memory else 'local',demo=demo,meeting_key=None if demo else '/aaa-bbbb-ccc'))
    assert result.status_code==201,result.text
    return result.json()
def until(client,path,predicate):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        response=client.get(path);assert response.status_code==200,response.text
        data=response.json()
        if predicate(data):return data
        time.sleep(.01)
    raise AssertionError(f'Job did not complete: {path}')
def authenticate(ws):
    ws.send_json({'type':'auth','protocol_version':1,'token':'test-pairing-token'})
    assert ws.receive_json()['type']=='auth.ok'
def bind(ws,id,tab=1,doc='doc-1'):
    ws.send_json(dict(type='session.bind',protocol_version=1,session_id=id,payload=dict(tab_id=tab,document_id=doc,meeting_key='/aaa-bbbb-ccc')))
    result=ws.receive_json();assert result['type']=='session.snapshot',result

@pytest.mark.acceptance('SEC-01','SEC-06')
def test_http_auth_host_origin_and_secret_redaction(client):
    assert client.get('/health',headers={'Authorization':''}).json()=={'status':'ok','protocol_version':1,'fts5':True}
    assert client.get('/api/v1/projects',headers={'Authorization':''}).status_code==401
    assert client.get('/api/v1/projects',headers={'Origin':'https://attacker.example'}).status_code==403
    assert client.get('/health',headers={'Host':'attacker.example'}).status_code==403
    assert client.get('/openapi.json',headers={'Authorization':''}).status_code==401
    sentinel='SENTINEL_FAKE_API_SECRET'
    assert client.put('/api/v1/provider/credential',json={'api_key':sentinel}).json()=={'has_key':True}
    settings=client.get('/api/v1/settings')
    assert settings.json()['has_key'] and sentinel not in settings.text
    assert sentinel not in client.get('/api/v1/metrics').text
    bad=client.put('/api/v1/provider/credential',json={'api_key':sentinel,'unexpected':sentinel})
    assert bad.status_code==422 and sentinel not in bad.text
    for file in client.app.state.store.disk.execute('SELECT payload FROM settings'):assert sentinel not in file[0]
    assert client.delete('/api/v1/provider/credential').json()=={'has_key':False}

@pytest.mark.acceptance('SEC-01')
def test_websocket_first_frame_auth_and_exact_origin(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/v1/events',headers={'Origin':'https://attacker.example'}):pass
    with client.websocket_connect('/api/v1/events',headers=WS_HEADERS) as ws:
        ws.send_json({'type':'caption.upsert','payload':caption()})
        assert ws.receive_json()['type']=='auth.error'
    assert client.app.state.store.disk.execute('SELECT count(*) FROM caption_segments').fetchone()[0]==0
    with client.websocket_connect('/api/v1/events',headers=WS_HEADERS) as ws:
        ws.send_json({'type':'auth','protocol_version':1,'token':'wrong'})
        assert ws.receive_json()['type']=='auth.error'

@pytest.mark.acceptance('TRN-01','TRN-02','TRN-03','TRN-04')
def test_ws_reconnect_retry_and_tab_document_scope(client):
    p=project(client);m=meeting(client,p);e=caption(revision=4,seq=4,text='NOT on Friday')
    with client.websocket_connect('/api/v1/events',headers=WS_HEADERS) as ws:
        authenticate(ws);bind(ws,m['id'])
        ws.send_json(dict(type='caption.upsert',protocol_version=1,session_id=m['id'],payload=e));ack=ws.receive_json();assert ack['type']=='caption.ack' and ack['applied'];assert ws.receive_json()['type']=='caption.updated'
    with client.websocket_connect('/api/v1/events',headers=WS_HEADERS) as ws:
        authenticate(ws);bind(ws,m['id'])
        for _ in range(2):
            ws.send_json(dict(type='caption.upsert',protocol_version=1,session_id=m['id'],payload=e));assert ws.receive_json()['event_id']==e['event_id']
        older=caption(revision=3,seq=3,text='on Friday')
        ws.send_json(dict(type='caption.upsert',protocol_version=1,session_id=m['id'],payload=older));assert not ws.receive_json()['applied']
        ws.send_json(dict(type='session.bind',protocol_version=1,session_id=m['id'],payload=dict(tab_id=2,document_id='wrong',meeting_key='/aaa-bbbb-ccc')))
        assert ws.receive_json()['payload']['code']=='BINDING_SCOPE'
    snapshot=client.get('/api/v1/meetings/'+m['id']).json()
    assert len(snapshot['segments'])==1 and snapshot['segments'][0]['text']=='NOT on Friday'
    assert snapshot['transcript_revision']==1
    assert any(g['reason']=='transport_disconnected' for g in snapshot['gaps'])

@pytest.mark.acceptance('CAP-05','CAP-06')
def test_caption_status_is_not_inferred_from_silence(client):
    m=meeting(client,project(client))
    with client.websocket_connect('/api/v1/events',headers=WS_HEADERS) as ws:
        authenticate(ws);bind(ws,m['id'])
        for status in ('waiting_for_caption','captions_off','unknown'):
            ws.send_json(dict(type='capture.status',protocol_version=1,session_id=m['id'],payload={'status':status}))
            assert ws.receive_json()['payload']['status']==status
            ws.send_json(dict(type='heartbeat',protocol_version=1,payload={}))
            assert ws.receive_json()['type']=='heartbeat'
            assert client.get('/api/v1/meetings/'+m['id']).json()['capture_status']==status

@pytest.mark.acceptance('TRN-01')
def test_invalid_caption_has_correlated_error_and_does_not_poison_connection(client):
    m=meeting(client,project(client))
    with client.websocket_connect('/api/v1/events',headers=WS_HEADERS) as ws:
        authenticate(ws);bind(ws,m['id']);bad=caption(text='x'*10001)
        ws.send_json(dict(type='caption.upsert',protocol_version=1,session_id=m['id'],event_id=bad['event_id'],payload=bad))
        error=ws.receive_json();assert error['type']=='error' and error['event_id']==bad['event_id'] and error['payload']['code']=='INVALID_EVENT'
        good=caption();ws.send_json(dict(type='caption.upsert',protocol_version=1,session_id=m['id'],event_id=good['event_id'],payload=good));assert ws.receive_json()['type']=='caption.ack';assert ws.receive_json()['type']=='caption.updated'
    assert len(client.get('/api/v1/meetings/'+m['id']).json()['segments'])==1

@pytest.mark.acceptance('REP-02','HIS-01','REP-03')
def test_demo_report_edit_regenerate_conflict_and_exact_version_export(client):
    p=project(client);m=meeting(client,p,demo=True);id=m['id']
    assert client.post(f'/api/v1/meetings/{id}/demo-caption',json=caption(text='Maybe Monday. No owner confirmed.')).status_code==200
    end=client.post(f'/api/v1/meetings/{id}/control',json=dict(action='end',idempotency_key=uid())).json()
    def generate():
        job=client.post(f'/api/v1/meetings/{id}/reports',json={'transcript_revision':end['transcript_revision']}).json()
        done=until(client,'/api/v1/jobs/'+job['id'],lambda d:d['status'] in ('ready','error'))
        assert done['status']=='ready',done
        return client.get('/api/v1/reports/'+done['report_id']).json()
    initial=generate();edited_payload=initial['payload'];edited_payload['summary_vi']='USER_EDIT_PRESERVED'
    edited=client.patch('/api/v1/reports/'+initial['id'],json=dict(expected_version=initial['version'],payload=edited_payload,reviewed=True))
    assert edited.status_code==200,edited.text
    assert edited.json()['version']==2 and edited.json()['reviewed_at']
    regenerated=generate();assert regenerated['version']==3
    previous=client.get('/api/v1/reports/'+edited.json()['id']).json()
    assert previous['payload']['summary_vi']=='USER_EDIT_PRESERVED'
    conflict=client.patch('/api/v1/reports/'+initial['id'],json=dict(expected_version=1,payload=edited_payload))
    assert conflict.status_code==409 and conflict.json()['current_version']==3
    exported=client.get('/api/v1/reports/'+previous['id']+'/export?format=json').json()
    assert exported==previous
    markdown=client.get('/api/v1/reports/'+previous['id']+'/export?format=markdown').text
    assert 'USER_EDIT_PRESERVED' in markdown and 'DEMO' in markdown and 'Evidence:' in markdown
    assert client.get('/api/v1/meetings',params={'query':'Maybe Monday','project_id':p['id']}).json()[0]['id']==id

@pytest.mark.acceptance('CIT-01','AI-04')
def test_citation_snapshots_survive_resync_and_mark_deleted(client,tmp_path):
    p=project(client);path=tmp_path/'notes.md';path.write_text('API-17 V1 needs staging testing',encoding='utf8')
    imported=client.post('/api/v1/projects/'+p['id']+'/sources',json=dict(kind='text',title='Notes',local_path=str(path))).json()
    assert imported['job']['status']=='ready',imported
    m=meeting(client,p,demo=True);id=m['id']
    client.post(f'/api/v1/meetings/{id}/demo-caption',json=caption(text='API-17 status?'))
    client.post(f'/api/v1/meetings/{id}/suggest',json={'action':'suggest'})
    snapshot=until(client,f'/api/v1/meetings/{id}',lambda d:len(d['suggestions'])==1)
    sid=snapshot['suggestions'][0]['id'];url=f'/api/v1/meetings/{id}/suggestions/{sid}/citations'
    assert 'V1' in client.get(url).json()[0]['content']
    path.write_text('API-17 V2 approved for review',encoding='utf8');client.post('/api/v1/sources/'+imported['source_id']+'/reindex')
    after=client.get(url).json()[0];assert 'V1' in after['content'] and after['source_changed']
    client.delete('/api/v1/sources/'+imported['source_id'])
    gone=client.get(url).json()[0];assert gone['source_deleted'] and 'V1' in gone['content']

@pytest.mark.acceptance('SEC-03','SEC-05')
def test_project_delete_cascades_chunks_and_full_meeting(client):
    p=project(client);id=meeting(client,p,demo=True)['id']
    client.post('/api/v1/projects/'+p['id']+'/sources',json=dict(kind='text',title='Doc',pasted_text='DELETE_INDEX_SENTINEL'))
    client.post(f'/api/v1/meetings/{id}/demo-caption',json=caption())
    client.delete('/api/v1/projects/'+p['id'])
    assert client.get(f'/api/v1/meetings/{id}').status_code==404
    for table in ('projects','sources','chunks','chunks_fts','meetings','caption_segments','applied_events','capture_gaps','ai_requests','suggestions','reports'):
        assert client.app.state.store.disk.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0

@pytest.mark.acceptance('OPS-01','SCP-01')
def test_production_never_falls_back_to_mock_and_manifest_has_no_audio(client):
    m=meeting(client,project(client));id=m['id']
    assert client.post(f'/api/v1/meetings/{id}/demo-caption',json=caption()).status_code==403
    response=client.post('/api/v1/provider/test')
    assert response.status_code==422 and response.json()['code']=='PROVIDER_KEY_MISSING'
    from pathlib import Path
    manifest=json.loads((Path(__file__).resolve().parents[2]/'extension/public/manifest.json').read_text('utf8'))
    assert not {'tabCapture','audioCapture','offscreen','microphone'}.intersection(manifest['permissions'])
    assert manifest['content_scripts'][0]['matches']==['https://meet.google.com/*']
    assert '<all_urls>' not in manifest['host_permissions']
