import json
import pytest
from app.storage import Storage, uid
from tests.conftest import caption


@pytest.mark.parametrize('mode', ['local', 'memory'])
def test_raw_text_retry_and_reverse_revision_preserve_transcript(store, project, mode):
    m=store.create_meeting(dict(project_id=project['id'],title='Capture',timezone='UTC',persistence_mode=mode,demo=False,meeting_key='/capture'))
    raw='  Không  đổi 15.5 ms\nAPI-17 — ✓  '
    newest=caption(raw,revision=3,seq=3)
    first=store.apply_caption(m['id'],newest)
    assert first['applied']
    assert store.apply_caption(m['id'],newest)==first  # apply succeeded, ACK was lost
    assert not store.apply_caption(m['id'],caption('obsolete 50 ms',revision=1,seq=1))['applied']
    assert not store.apply_caption(m['id'],caption('obsolete 15 ms',revision=2,seq=2))['applied']
    segments=store.transcript(m['id'])
    assert len(segments)==1 and segments[0]['text']==raw and segments[0]['revision']==3
    assert store.meeting(m['id'])['transcript_revision']==1
    assert store.snapshot(m['id'])['requests']==[]
    if mode=='memory':assert store.disk.execute('SELECT count(*) FROM caption_segments').fetchone()[0]==0


@pytest.mark.parametrize('action', ['pause','end','interrupt'])
def test_control_with_pending_loss_records_gap_and_never_applies_paused_content(store, meeting, action):
    id=meeting['id'];store.apply_caption(id,caption('Before control'))
    result=store.control(id,dict(action=action,idempotency_key=uid(),reason='interrupted_pending_discarded'))
    during=caption('MUST NOT BE SAVED',segment='during')
    assert not store.apply_caption(id,during)['applied']
    assert [s['text'] for s in store.transcript(id)]==['Before control']
    assert any(g['reason']=='interrupted_pending_discarded' for g in store.gaps(id))
    if action!='end':
        store.control(id,dict(action='resume',idempotency_key=uid()))
        assert not store.apply_caption(id,during)['applied']  # discarded event ACK replay remains discarded
        store.apply_caption(id,caption('After resume',segment='after',seq=3))
        assert [s['text'] for s in store.transcript(id)]==['Before control','After resume']


@pytest.mark.parametrize('mode', ['local','memory'])
def test_backend_restart_interrupts_disk_and_loses_ram_without_promoting_it(tmp_path,mode):
    path=tmp_path/'restart';s=Storage(path)
    p=s.create_project(dict(name='P',description='',glossary={}))
    m=s.create_meeting(dict(project_id=p['id'],title='Restart',timezone='UTC',persistence_mode=mode,demo=False,meeting_key='/restart'))
    s.apply_caption(m['id'],caption('Before restart'));s.close()
    s=Storage(path)
    try:
        if mode=='local':
            assert s.meeting(m['id'])['status']=='interrupted'
            assert s.transcript(m['id'])[0]['text']=='Before restart'
            assert not s.apply_caption(m['id'],caption('Disconnected text',segment='no'))['applied']
        else:
            assert s.meetings()==[]
            assert s.disk.execute('SELECT count(*) FROM caption_segments').fetchone()[0]==0
    finally:s.close()


def receive(ws,kind):
    for _ in range(30):
        msg=ws.receive_json()
        if msg['type']==kind:return msg
    raise AssertionError(f'Missing {kind}')


def test_obsolete_document_socket_cannot_write_after_rebind(client):
    p=client.post('/api/v1/projects',json=dict(name='P')).json()
    m=client.post('/api/v1/meetings',json=dict(project_id=p['id'],title='scope',meeting_key='/scope')).json()
    def bind(ws,doc):
        ws.send_json(dict(type='auth',protocol_version=1,token='test-pairing-token'));receive(ws,'auth.ok')
        ws.send_json(dict(type='session.bind',protocol_version=1,session_id=m['id'],payload=dict(tab_id=1,document_id=doc,meeting_key='/scope')));receive(ws,'session.snapshot')
    origin={'Origin':'chrome-extension://'+'a'*32,'Host':'127.0.0.1:8765'}
    with client.websocket_connect('/api/v1/events',headers=origin) as old:
        bind(old,'old-document')
        with client.websocket_connect('/api/v1/events',headers=origin) as new:
            bind(new,'new-document')
            e=caption('Old document must not leak')
            old.send_json(dict(type='caption.upsert',protocol_version=1,session_id=m['id'],event_id=e['event_id'],payload=e))
            assert receive(old,'error')['payload']['code']=='BINDING_SCOPE'
            e=caption('New document only',segment='new')
            new.send_json(dict(type='caption.upsert',protocol_version=1,session_id=m['id'],event_id=e['event_id'],payload=e))
            ack=receive(new,'caption.ack');assert ack['backend_applied'] and ack['segment_revision']==1
            gap=dict(type='capture.gap',protocol_version=1,session_id=m['id'],payload=dict(reason='outbox_overflow',event_id='gap-id'))
            new.send_json(gap);first=receive(new,'capture.gap.ack')
            new.send_json(gap);assert receive(new,'capture.gap.ack')==first
            snap=client.get('/api/v1/meetings/'+m['id']).json()
            assert [s['text'] for s in snap['segments']]==['New document only']
            assert any(g['reason']=='document_reloaded' for g in snap['gaps'])
            assert sum(g['reason']=='outbox_overflow' for g in snap['gaps'])==1
    assert client.get('/api/v1/meetings/'+m['id']).json()['capture_status']=='disconnected'


def test_request_timing_tracks_validation_without_paid_provider(client):
    schemas=client.get('/openapi.json').json()['components']['schemas']
    assert {'CaptionAckDTO','CaptureGapAckDTO','CaptureDiagnosticsDTO','RequestTimingDTO'}.issubset(schemas)
    assert 'segment_revision' in schemas['CaptionAckDTO']['properties']
    assert 'pending_gap' in schemas['CaptureDiagnosticsDTO']['properties']
    p=client.post('/api/v1/projects',json=dict(name='P')).json()
    m=client.post('/api/v1/meetings',json=dict(project_id=p['id'],title='timing',demo=True)).json()
    client.post('/api/v1/meetings/'+m['id']+'/demo-caption',json=caption('Could you clarify the next step?'))
    rid=client.post('/api/v1/meetings/'+m['id']+'/suggest',json=dict(action='suggest')).json()['request_id']
    import time
    for _ in range(100):
        snap=client.get('/api/v1/meetings/'+m['id']).json()
        r=next(r for r in snap['requests'] if r['id']==rid)
        if r['status'] in ('ready','stale','error'):break
        time.sleep(.01)
    assert r['status']=='ready'
    timing=r['timing'];assert timing['provider_mode']=='demo' and timing['provider_ms']==0
    assert timing['validation_ms']>=0 and timing['outcome']=='ready'
    offsets=[m['offset_ms'] for m in timing['marks']]
    assert offsets==sorted(offsets) and offsets[0]==0
    assert 'validation_completed' in [m['stage'] for m in timing['marks']]
    records=client.get('/api/v1/metrics').json()['latency_records']
    assert any(r['request_id']==rid for r in records)
    assert 'Could you' not in json.dumps(records)
