import json
import sqlite3
from datetime import datetime,timezone,timedelta
import pytest
from app.storage import Storage,uid,dumps
from app.errors import AppError
from .conftest import caption

@pytest.mark.acceptance('TRN-01','TRN-02','CAP-01')
def test_ack_replay_and_late_revision_are_atomic(store,meeting):
    id=meeting['id'];e=caption(revision=4,seq=4,text='We will NOT deploy on Friday')
    first=store.apply_caption(id,e)
    assert store.apply_caption(id,e)==first==store.apply_caption(id,e)
    store.apply_caption(id,caption(revision=3,seq=3,text='We will deploy on Friday'))
    assert store.transcript(id)[0]['text']=='We will NOT deploy on Friday'
    assert store.meeting(id)['transcript_revision']==1
    assert store.disk.execute('SELECT count(*) FROM applied_events').fetchone()[0]==2
    assert len(store.transcript(id))==1

@pytest.mark.acceptance('CAP-02','CAP-03')
def test_identical_real_turns_are_not_global_deduplicated(store,meeting):
    a=caption(text='Yes',segment='a');b=caption(text='Yes',segment='b',seq=2);b['speaker_label']='Other'
    for e in (a,b,caption(text='No',segment='c',seq=3),caption(text='Yes',segment='d',seq=4)):store.apply_caption(meeting['id'],e)
    assert [s['text'] for s in store.transcript(meeting['id'])]==['Yes','Yes','No','Yes']

@pytest.mark.acceptance('SES-01','SES-02')
def test_pause_never_persists_text_resume_gap_and_idempotent_end(store,meeting):
    id=meeting['id'];store.apply_caption(id,caption())
    store.control(id,dict(action='pause',idempotency_key='pause'))
    secret=caption(text='MUST_NOT_PERSIST_PAUSED_CONTENT',segment='paused',seq=2)
    assert store.apply_caption(id,secret)['ignored_reason']=='paused'
    store.control(id,dict(action='resume',idempotency_key='resume'))
    store.apply_caption(id,caption(text='Resume now',segment='resumed',seq=3))
    end=store.control(id,dict(action='end',idempotency_key='end',reason='end_flush_timeout'))
    assert store.control(id,dict(action='end',idempotency_key='end'))==end
    assert store.control(id,dict(action='end',idempotency_key='again'))['ended_at']==end['ended_at']
    assert any(g['reason']=='pause' and g['to_at'] for g in store.gaps(id))
    assert any(g['reason']=='end_flush_timeout' for g in store.gaps(id))
    assert secret['text'] not in dumps(store.snapshot(id))

@pytest.mark.acceptance('SEC-02','SEC-06')
def test_memory_transcript_and_report_snapshots_do_not_touch_disk(tmp_path):
    s=Storage(tmp_path);p=s.create_project(dict(name='Persist project',description='',glossary={}))
    m=s.create_meeting(dict(project_id=p['id'],title='RAM title sentinel',timezone='UTC',persistence_mode='memory',demo=True,meeting_key=None))
    s.apply_caption(m['id'],caption(text='RAM_TRANSCRIPT_SENTINEL'))
    s.control(m['id'],dict(action='end',idempotency_key='end'))
    with s.ram:
        s.ram.execute('INSERT INTO ai_requests VALUES(?,?,?)',('r',m['id'],dumps({'text':'RAM_REQUEST_SENTINEL'})))
        s.ram.execute('INSERT INTO reports VALUES(?,?,?,?)',('rep',m['id'],1,dumps({'text':'RAM_REPORT_SENTINEL'})))
    assert s.disk.execute('SELECT count(*) FROM meetings').fetchone()[0]==0
    s.close()
    for path in tmp_path.glob('*'):
        assert b'RAM_TRANSCRIPT_SENTINEL' not in path.read_bytes()
        assert b'RAM_REPORT_SENTINEL' not in path.read_bytes()
    reopened=Storage(tmp_path)
    assert reopened.meetings()==[] and len(reopened.projects())==1
    reopened.close()

@pytest.mark.acceptance('TRN-04')
def test_restart_preserves_sources_and_captions_and_marks_interrupted(tmp_path):
    s=Storage(tmp_path);p=s.create_project(dict(name='A',description='',glossary={}))
    m=s.create_meeting(dict(project_id=p['id'],title='Persistent',timezone='UTC',persistence_mode='local',demo=False,meeting_key='/meet'))
    s.apply_caption(m['id'],caption());s.close();s=Storage(tmp_path)
    assert s.meeting(m['id'])['status']=='interrupted'
    assert s.transcript(m['id'])[0]['text']=='Can we deploy?'
    assert s.gaps(m['id'])[0]['reason']=='backend_restart';s.close()

@pytest.mark.acceptance('SEC-03','SEC-05')
def test_retention_and_delete_cascade_preserve_project_sources(store,meeting):
    from app.ingestion import Ingestion
    id=meeting['id'];store.apply_caption(id,caption());m=store.meeting(id)
    m['started_at']=(datetime.now(timezone.utc)-timedelta(days=31)).isoformat()
    m['status']='ended';m['ended_at']=m['started_at']
    with store.disk:store.save_meeting(store.disk,m)
    source=Ingestion(store).add(m['project_id'],dict(kind='text',title='Retained source',pasted_text='PROJECT_SOURCE_MUST_REMAIN'))
    assert Ingestion(store).sync(source['id'])['status']=='ready'
    fresh=store.create_meeting({k:v for k,v in meeting.items() if k in ('project_id','title','timezone','persistence_mode','demo','meeting_key')})
    assert id in store.cleanup()
    assert store.meeting(fresh['id'])['status']=='active'
    for table in ('caption_segments','applied_events','capture_gaps','controls'):
        assert store.disk.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0
    assert len(store.projects())==1
    assert store.source(source['id'])['status']=='ready' and store.disk.execute('SELECT count(*) FROM chunks').fetchone()[0]==1
    assert store.disk.execute('PRAGMA foreign_key_check').fetchall()==[]

@pytest.mark.acceptance('TRN-02')
def test_segment_cannot_cross_capture_epochs(store,meeting):
    store.apply_caption(meeting['id'],caption())
    e=caption(revision=2,seq=2);e['capture_epoch']='other-epoch'
    with pytest.raises(AppError,match='different capture epoch'):store.apply_caption(meeting['id'],e)
    assert store.meeting(meeting['id'])['transcript_revision']==1

def test_only_one_active_meeting_and_invalid_state_are_rejected(store,meeting):
    with pytest.raises(AppError):store.create_meeting({k:v for k,v in meeting.items() if k in ('project_id','title','timezone','persistence_mode','demo','meeting_key')})
    with pytest.raises(AppError):store.control(meeting['id'],dict(action='resume',idempotency_key=uid()))
