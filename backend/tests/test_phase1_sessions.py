import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import time

import pytest
from app.errors import AppError
from app.storage import uid

def create(store, project, mode='local'):
    return store.create_meeting(dict(project_id=project['id'], title='Session invariant',
        timezone='UTC', persistence_mode=mode, demo=False, meeting_key='/fixture'))

def control(store, meeting, action, key=None):
    return store.control(meeting['id'], dict(action=action, idempotency_key=key or uid()))

def test_http_interrupted_resume_cannot_steal_active_slot(client):
    project=client.post('/api/v1/projects', json={'name':'Phase 1'}).json()
    def start(mode):
        response=client.post('/api/v1/meetings',json=dict(project_id=project['id'],title='Test',persistence_mode=mode))
        assert response.status_code==201
        return response.json()['id']
    a=start('local')
    assert client.post(f'/api/v1/meetings/{a}/control',json={'action':'interrupt','idempotency_key':'interrupt'}).status_code==200
    b=start('memory')
    before_a=client.get(f'/api/v1/meetings/{a}').json()
    before_b=client.get(f'/api/v1/meetings/{b}').json()
    response=client.post(f'/api/v1/meetings/{a}/control',json={'action':'resume','idempotency_key':'resume'})
    assert response.status_code==409, response.text
    assert response.json()['code']=='ACTIVE_MEETING'
    assert client.get(f'/api/v1/meetings/{a}').json()==before_a
    assert client.get(f'/api/v1/meetings/{b}').json()==before_b

@pytest.mark.parametrize('a_mode,b_mode',[('local','local'),('local','memory'),('memory','local'),('memory','memory')])
@pytest.mark.parametrize('b_status',['active','paused'])
def test_resume_checks_both_stores_and_preserves_rejected_sessions(store,project,a_mode,b_mode,b_status):
    a=create(store,project,a_mode)
    from .conftest import caption
    store.apply_caption(a['id'],caption(text='A transcript must survive rejection.'))
    current=store.meeting(a['id'])
    current['binding']=dict(tab_id=101,document_id='document-a',meeting_key='/fixture')
    with store.db_for(a['id']):store.save_meeting(store.db_for(a['id']),current)
    control(store,a,'interrupt')
    b=create(store,project,b_mode)
    store.apply_caption(b['id'],caption(text='B transcript must survive rejection.'))
    current=store.meeting(b['id'])
    current['binding']=dict(tab_id=202,document_id='document-b',meeting_key='/fixture')
    with store.db_for(b['id']):store.save_meeting(store.db_for(b['id']),current)
    if b_status=='paused':control(store,b,'pause')
    before=[copy.deepcopy(store.snapshot(m['id'])) for m in (a,b)]
    with pytest.raises(AppError) as failure:control(store,a,'resume','retry-same-key')
    assert failure.value.status==409 and failure.value.code=='ACTIVE_MEETING'
    assert [store.snapshot(m['id']) for m in (a,b)]==before
    control(store,b,'end')
    assert control(store,a,'resume','retry-same-key')['status']=='active'
    gaps=len(store.gaps(a['id']))
    assert control(store,a,'resume','retry-same-key')['status']=='active'
    assert len(store.gaps(a['id']))==gaps

@pytest.mark.parametrize('mode',['local','memory'])
@pytest.mark.parametrize('status',['active','paused'])
def test_create_cannot_bypass_slot_in_either_store(store,project,mode,status):
    a=create(store,project,mode)
    if status=='paused':control(store,a,'pause')
    with pytest.raises(AppError) as failure:create(store,project,'memory' if mode=='local' else 'local')
    assert failure.value.status==409
    assert len(store.meetings())==1

def test_idempotent_resume_replay_does_not_reactivate_interrupted_session(store,project):
    a=create(store,project)
    control(store,a,'pause')
    original=control(store,a,'resume','resume-once')
    control(store,a,'interrupt')
    b=create(store,project,'memory')
    before=store.snapshot(a['id'])
    assert control(store,a,'resume','resume-once')==original
    assert store.snapshot(a['id'])==before and store.meeting(b['id'])['status']=='active'

def test_ended_session_cannot_resume(store,project):
    a=create(store,project)
    control(store,a,'end')
    before=store.snapshot(a['id'])
    with pytest.raises(AppError) as failure:control(store,a,'resume')
    assert failure.value.code=='INVALID_STATE' and failure.value.status==409
    assert store.snapshot(a['id'])==before

@pytest.mark.parametrize('operation',['create_create','create_resume','resume_resume'])
def test_competing_transitions_have_one_winner(store,project,monkeypatch,operation):
    a=create(store,project)
    control(store,a,'interrupt')
    b=create(store,project,'memory')
    control(store,b,'interrupt')
    original=store.meetings
    def slow_snapshot():
        value=original()
        time.sleep(.02)  # Widen the real check/write race without a barrier inside the lock.
        return value
    monkeypatch.setattr(store,'meetings',slow_snapshot)
    start=Barrier(2)
    def run(index):
        start.wait(timeout=3)
        try:
            if operation=='create_create' or (operation=='create_resume' and index==0):
                create(store,project,'local' if index==0 else 'memory')
            else:control(store,a if index==1 else b,'resume')
            return 'ok'
        except AppError as error:
            assert error.code=='ACTIVE_MEETING' and error.status==409
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(run,[0,1]))
    assert sorted(outcomes)==['conflict','ok']
    assert sum(m['status'] in ('active','paused') for m in original())==1
