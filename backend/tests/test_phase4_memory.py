import json
import sqlite3
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from app import meeting_memory as mm
from app.storage import Storage,uid
from app.errors import AppError
from app.retrieval import Retrieval,Semantic
from app.service import Service
from app.llm import demo_suggestion,validate_suggestion
from .conftest import caption

ROOT=Path(__file__).resolve().parents[2]
CORPUS=json.loads((ROOT/'fixtures/phase4/meeting-memory.json').read_text('utf8'))

def apply(store,m,text,segment='s',revision=1,speaker='Minh',stable=True,seq=1,observed_at='2026-10-19T00:30:00+00:00'):
    e=caption(text,segment=segment,revision=revision,seq=seq);e.update(speaker_label=speaker,stable=stable,observed_at=observed_at)
    return store.apply_caption(m['id'],e)

@pytest.mark.parametrize('case',[c for c in CORPUS['cases'] if c['split']=='tuning'],ids=lambda c:c['id'])
def test_predeclared_tuning_states_owner_due_scope(store,meeting,case):
    for n,e in enumerate(case['events']):apply(store,meeting,e['text'],e['segment'],e['revision'],e['speaker'],e['stable'],n+1,e['observed_at'])
    keys=('kind','entity','status','owner','normalized_due','environment')
    assert [{k:i.get(k) for k in keys} for i in store.memory(meeting['id'])]==case['expected']
    for item in store.memory(meeting['id']):
        assert item['meeting_id']==meeting['id'] and item['project_id']==meeting['project_id']
        assert all(store.evidence_revision(meeting['id'],e['segment_id'],e['revision']) for e in item['evidence'])

def test_partial_and_speaker_correction_invalidate_and_keep_exact_history(store,meeting):
    apply(store,meeting,'I will review API-17 by tomorrow.')
    original=store.memory(meeting['id'])[0];assert original['owner']=='Minh'
    apply(store,meeting,'I will review API-17 by tomorrow.',revision=2,speaker=None,stable=False,seq=2)
    assert store.memory(meeting['id'])[0]['status']=='invalidated'
    assert store.evidence_revision(meeting['id'],'s',1)['speaker']=='Minh'
    apply(store,meeting,'I can review API-17.',revision=3,speaker='Alex',seq=3)
    item=store.memory(meeting['id'])[0];assert item['owner'] is None and item['kind']=='proposal'
    versions=[json.loads(r[0]) for r in store.db_for(meeting['id']).execute('SELECT payload FROM memory_versions ORDER BY version')]
    assert [i['status'] for i in versions]==['accepted','invalidated','proposed'] and item['id']==original['id']

def test_memory_edit_is_not_spoken_and_conflict_and_correction(store,meeting):
    apply(store,meeting,'I will review API-17 by tomorrow.');db=store.db_for(meeting['id']);m=store.meeting(meeting['id']);item=store.memory(m['id'])[0]
    with db:edited=mm.edit(db,m,item['id'],dict(owner='Alex',status='cancelled',raw_due_text='Maybe Friday'),item['version']);store.save_meeting(db,m)
    assert edited['origin']=='user_edit' and edited['normalized_due'] is None
    assert edited['edit_provenance']['changed_fields']==['owner','raw_due_text','status']
    with pytest.raises(AppError,match='Memory changed'):mm.edit(db,m,item['id'],dict(owner='Other'),1)
    apply(store,m,'I will review API-17.',revision=2,seq=2)
    assert store.memory(m['id'])[0]['origin']=='user_edit' and store.memory(m['id'])[0]['status']=='invalidated'

def test_relative_due_uses_observed_day_not_current_clock():
    assert mm.due_value('tomorrow',dict(observed_to='2026-10-19T00:30:00Z'),'America/Los_Angeles',True)[0]=='2026-10-19'
    for raw in ('next Friday','early next week','2026-02-30'):
        assert mm.due_value(raw,dict(observed_to='2026-10-19T00:30:00Z'),'America/Los_Angeles',True)[0] is None

def test_no_id_production_correction_and_unbound_denial_are_not_confirmed(store,meeting):
    apply(store,meeting,'We approved production.',speaker='Client')
    assert store.memory(meeting['id'])[0]['status']=='confirmed'
    apply(store,meeting,'We have NOT approved production.',revision=2,speaker='Client',seq=2)
    assert store.memory(meeting['id'])[0]['status']=='unconfirmed'
    apply(store,meeting,'Confirmed: deploy API-17.',segment='specific',speaker='Client',seq=3)
    apply(store,meeting,'We have not approved it.',segment='denial',speaker='QA',seq=4)
    assert next(i for i in store.memory(meeting['id']) if i['entity']=='API-17')['status']=='disputed'
    assert store.memory(meeting['id'])[-1]['entity'] is None

def test_bare_yes_does_not_turn_a_request_into_owner_acceptance(store,meeting):
    apply(store,meeting,'Minh, can you review API-17?',speaker='Client')
    apply(store,meeting,'Yes.',segment='answer',speaker='Minh',seq=2)
    assert not any(i['owner'] or i['status']=='accepted' for i in store.memory(meeting['id']))
    assert store.memory(meeting['id'])[-1]['kind']=='spoken_fact'

def test_same_owner_explicit_negative_cancels_own_task_not_another_task(store,meeting):
    apply(store,meeting,'I will review API-17.')
    apply(store,meeting,'I will test API-71.',segment='second',seq=2)
    apply(store,meeting,'I will not review API-17.',segment='withdraw',seq=3)
    items=store.memory(meeting['id']);assert items[0]['status']=='cancelled' and items[1]['status']=='accepted' and items[2]['status']=='cancelled'

@pytest.mark.parametrize('text',['Once approved, I will deploy API-17.','Assuming QA passes, I will deploy API-17.','After approval I will deploy API-17.','Alex told me "I will review API-17".'])
def test_conditional_or_reported_speech_never_assigns_speakers_owner(store,meeting,text):
    apply(store,meeting,text,speaker='Client');item=store.memory(meeting['id'])[0]
    assert item['owner'] is None and item['status'] not in ('accepted','confirmed')

def test_mentioned_date_not_deadline_and_past_due_not_completed(store,meeting):
    apply(store,meeting,'API-17 incident happened on 2026-10-18.')
    assert store.memory(meeting['id'])[0]['raw_due_text'] is None
    apply(store,meeting,'I will review API-71 by 2020-01-01.',segment='old-due',seq=2)
    assert store.memory(meeting['id'])[1]['status']=='accepted'

def test_explicit_task_acceptance_links_request_without_assigning_request_owner(store,meeting):
    apply(store,meeting,'Can you review API-17?',speaker='Client')
    apply(store,meeting,'I will review API-17.',segment='accept',speaker='Minh',seq=2)
    requested,accepted=store.memory(meeting['id'])
    assert requested['owner'] is None and requested['relations']==[dict(type='accepted_by',item_id=accepted['id'])]
    assert not mm.current(requested) and mm.current(accepted) and accepted['owner']=='Minh'

@pytest.mark.parametrize('owner,valid',[('Minh',True),('Alex',False)])
def test_live_named_owner_needs_that_speakers_acceptance_not_another_owner(store,meeting,owner,valid):
    apply(store,meeting,'I will review API-17.',speaker='Minh')
    snapshot=dict(segments=store.transcript(meeting['id']),memory=[],structured_memory=store.memory(meeting['id']),sources=[],self_speaker='Minh',sentence_limit=3,transcript_revision=1)
    payload=demo_suggestion(snapshot);payload.reply_en=f'{owner} will review API-17.'
    if valid:validate_suggestion(payload,snapshot)
    else:
        with pytest.raises(AppError) as error:validate_suggestion(payload,snapshot)
        assert error.value.code=='AI_TASK'

def test_live_context_early_memory_and_cache_revision(store,meeting):
    apply(store,meeting,'Confirmed: test API-17 in staging.',speaker='Client')
    for n in range(16):apply(store,meeting,'Ordinary discussion.',segment=f'noise{n}',seq=n+2,observed_at='2026-10-19T01:30:00Z')
    apply(store,meeting,'Which environment for API-17?',segment='question',seq=18,observed_at='2026-10-19T01:31:00Z')
    service=Service(store,Retrieval(store,Semantic(Path('.'))),None)
    snapshot=service.prepare(meeting['id'],dict(action='suggest'));assert 's' not in {s['id'] for s in snapshot['segments']}
    assert snapshot['structured_memory'] and 's' in {s['id'] for s in snapshot['memory']}
    db=store.db_for(meeting['id']);m=store.meeting(meeting['id']);item=store.memory(m['id'])[0]
    with db:mm.edit(db,m,item['id'],dict(status='cancelled'),item['version']);store.save_meeting(db,m)
    after=service.prepare(m['id'],dict(action='suggest'));assert after['input_hash']!=snapshot['input_hash']
    payload=demo_suggestion(after);payload.reply_en='API-17 is approved for staging.'
    with pytest.raises(AppError) as error:validate_suggestion(payload,after)
    assert error.value.code=='AI_MEMORY_STATE'

def test_manual_owner_annotation_is_not_participant_acceptance_in_live(store,meeting):
    apply(store,meeting,'I will review API-17.');db=store.db_for(meeting['id']);m=store.meeting(meeting['id']);item=store.memory(m['id'])[0]
    with db:mm.edit(db,m,item['id'],dict(owner='Alex'),item['version']);store.save_meeting(db,m)
    service=Service(store,Retrieval(store,Semantic(Path('.'))),None);snapshot=service.prepare(m['id'],dict(action='suggest',question='Who owns API-17?'));payload=demo_suggestion(snapshot);payload.reply_en='Alex will review API-17.'
    with pytest.raises(AppError) as error:validate_suggestion(payload,snapshot)
    assert error.value.code=='AI_MEMORY_ORIGIN'

@pytest.mark.parametrize('reply',['I will deploy.','Tôi sẽ triển khai.'])
def test_cancelled_task_cannot_resurrect_from_legacy_memory_or_omit_ticket_id(store,meeting,reply):
    apply(store,meeting,'I will deploy API-17.',segment='accepted');db=store.db_for(meeting['id']);m=store.meeting(meeting['id']);m['confirmed_segment_ids']=['accepted'];m['self_speaker']='Minh'
    with db:store.save_meeting(db,m)
    apply(store,meeting,'Cancel deploy API-17.',segment='cancel',seq=2)
    apply(store,meeting,'What should we do?',segment='question',speaker='Client',seq=3)
    service=Service(store,Retrieval(store,Semantic(Path('.'))),None);snapshot=service.prepare(m['id'],dict(action='suggest'))
    assert snapshot['memory_omitted_count']==1 and not any(s['id']=='accepted' for s in snapshot['memory'])
    assert any(i['status']=='cancelled' for i in snapshot['structured_memory'])
    payload=demo_suggestion(snapshot);payload.reply_en=reply
    with pytest.raises(AppError) as error:validate_suggestion(payload,snapshot)
    assert error.value.code=='AI_MEMORY_STATE'

def test_migration_preserves_version1_and_runs_once(tmp_path):
    db=sqlite3.connect(tmp_path/'copilot.sqlite3');db.executescript((ROOT/'backend/app/migrations/001.sql').read_text())
    db.execute('INSERT INTO projects VALUES(?,?,?,?,?)',('old','Old','kept','{}','2026-10-18'))
    old_meeting=dict(id='legacy',project_id='old',title='Legacy',status='ended',started_at='2026-10-18T00:00:00Z',ended_at='2026-10-18T01:00:00Z',timezone='UTC',persistence_mode='local',transcript_revision=1)
    old_report=dict(id='old-report',meeting_id='legacy',version=1,payload=dict(summary_vi='User saved legacy text'),user_edits=True)
    db.execute('INSERT INTO meetings VALUES(?,?,?)',('legacy','old',json.dumps(old_meeting)))
    db.execute('INSERT INTO reports VALUES(?,?,?,?)',('old-report','legacy',1,json.dumps(old_report)));db.commit();db.close()
    store=Storage(tmp_path);assert store.project('old')['description']=='kept'
    assert [r[0] for r in store.disk.execute('SELECT version FROM schema_version ORDER BY version')]==[1,2];store.close()
    store=Storage(tmp_path);assert store.project('old')['name']=='Old'
    assert store.objects('legacy','reports')==[old_report] and not store.memory('legacy')
    with pytest.raises(AppError):store.evidence_revision('legacy','unknown',1)
    store.close()

def test_multiple_revision_dependencies_invalidate_when_one_changes(store,meeting):
    apply(store,meeting,'I will review API-17.');apply(store,meeting,'Confirmed: test API-71 in staging.',segment='other',seq=2)
    item=store.memory(meeting['id'])[0];item['evidence'].append(dict(segment_id='other',revision=1))
    db=store.db_for(meeting['id'])
    with db:db.execute('UPDATE memory_items SET payload=? WHERE meeting_id=? AND id=?',(json.dumps(item),meeting['id'],item['id']))
    apply(store,meeting,'Production approval for test API-71 is pending.',segment='other',revision=2,seq=3)
    assert next(i for i in store.memory(meeting['id']) if i['id']==item['id'])['status']=='invalidated'

def test_editing_successor_and_later_caption_never_revives_superseded_decision(store,meeting):
    apply(store,meeting,'Confirmed: deploy API-17 on Friday.',segment='old',speaker='Client')
    apply(store,meeting,'Correction: confirmed deploy API-17 on Monday instead.',segment='new',speaker='Client',seq=2)
    db=store.db_for(meeting['id']);m=store.meeting(meeting['id']);successor=store.memory(m['id'])[1]
    with db:mm.edit(db,m,successor['id'],dict(owner='Alex'),successor['version']);store.save_meeting(db,m)
    apply(store,meeting,'API-99 has a separate status.',segment='unrelated',seq=3)
    old=store.memory(m['id'])[0];assert old['status']=='superseded' and not mm.current(old)
    apply(store,meeting,'Cancel deploy API-17.',segment='actual-cancel',speaker='Client',seq=4)
    assert not any(i['status']=='confirmed' and mm.current(i) for i in store.memory(m['id']))
    assert any(i['origin']=='transcript' and i['status']=='cancelled' for i in store.memory(m['id']))
    apply(store,meeting,'API-99 remains unrelated.',segment='later-noise',seq=5)
    items=store.memory(m['id']);assert items[0]['status']=='superseded'
    assert next(i for i in items if i['id']==successor['id'])['invalidation_reason']=='transcript_transition_changed'

def test_correction_after_user_edit_retains_note_and_derives_new_speech_lineage(store,meeting):
    apply(store,meeting,'Confirmed: deploy API-17 on Friday.',segment='old',speaker='Client')
    apply(store,meeting,'Correction: confirmed deploy API-17 on Monday instead.',segment='new',speaker='Client',seq=2)
    db=store.db_for(meeting['id']);m=store.meeting(meeting['id']);successor=store.memory(m['id'])[1]
    with db:mm.edit(db,m,successor['id'],dict(status='cancelled'),successor['version']);store.save_meeting(db,m)
    apply(store,meeting,'Cancel deploy API-17 because QA is not finished.',segment='new',revision=2,speaker='Client',seq=3)
    items=store.memory(m['id']);annotation=next(i for i in items if i['id']==successor['id']);speech=next(i for i in items if i.get('derived_after_user_edit')==successor['id'])
    assert annotation['origin']=='user_edit' and annotation['status']=='invalidated'
    assert speech['origin']=='transcript' and speech['evidence']==[dict(segment_id='new',revision=2)]
    assert not any(i['status']=='confirmed' and mm.current(i) for i in items)

def test_ram_memory_does_not_survive_backend_restart(tmp_path):
    store=Storage(tmp_path);p=store.create_project(dict(name='RAM restart',description='',glossary={}));m=store.create_meeting(dict(project_id=p['id'],title='RAM',timezone='UTC',persistence_mode='memory',demo=True));apply(store,m,'I will review API-17.')
    assert store.memory(m['id']);store.close();store=Storage(tmp_path)
    try:
        assert store.meetings()==[] and store.disk.execute('SELECT COUNT(*) FROM memory_versions').fetchone()[0]==0
    finally:store.close()

def test_ram_retention_and_cascade_no_disk_utterance(store,project):
    m=store.create_meeting(dict(project_id=project['id'],title='RAM',timezone='UTC',persistence_mode='memory',demo=False))
    text='I will review SECRET-1729 by tomorrow.';apply(store,m,text)
    assert store.memory(m['id']) and store.disk.execute('SELECT COUNT(*) FROM memory_items').fetchone()[0]==0
    assert store.disk.execute('SELECT COUNT(*) FROM segment_revisions').fetchone()[0]==0
    disk_file=Path(store.disk.execute('PRAGMA database_list').fetchone()['file'])
    assert all(text.encode() not in p.read_bytes() for p in disk_file.parent.glob('*.sqlite3*'))
    store.cleanup(datetime.now(timezone.utc)+timedelta(days=31))
    for table in ('memory_items','memory_versions','segment_revisions'):assert store.ram.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==0

def test_project_and_meeting_evidence_scopes(client):
    store=client.app.state.store;p=store.create_project(dict(name='Scope',description='',glossary={}))
    m=store.create_meeting(dict(project_id=p['id'],title='one',timezone='UTC',persistence_mode='local',demo=True));apply(store,m,'I will review API-17.')
    one=store.memory(m['id'])[0];store.control(m['id'],dict(action='end',idempotency_key=uid()))
    q=store.create_project(dict(name='Other',description='',glossary={}));other=store.create_meeting(dict(project_id=q['id'],title='two',timezone='UTC',persistence_mode='local',demo=True))
    assert client.get(f'/api/v1/meetings/{other["id"]}/memory').json()['items']==[]
    assert client.get(f'/api/v1/meetings/{other["id"]}/evidence/s?revision=1').status_code==404
    assert client.patch(f'/api/v1/meetings/{other["id"]}/memory/{one["id"]}',json=dict(expected_version=1,owner='Other')).status_code==404
    store.delete_project(p['id']);assert not store.disk.execute('SELECT 1 FROM memory_items WHERE project_id=?',(p['id'],)).fetchone()
