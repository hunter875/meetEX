import asyncio
import copy
from pathlib import Path
import pytest
from app.storage import uid
from app.service import Service
from app.retrieval import Retrieval,Semantic
from app.llm import demo_report
from app.models import ReportPayload,ReportEdit
from app.errors import AppError
from app.report_ledger import reconcile_report
from .test_phase4_memory import apply

class ReportProvider:
    def __init__(self):self.calls=[]
    async def complete(self,context,*args):
        self.calls.append(copy.deepcopy(context));return demo_report(context['segments'])

async def generate(store,meeting):
    provider=ReportProvider();service=Service(store,Retrieval(store,Semantic(Path('.'))),provider)
    store.control(meeting['id'],dict(action='end',idempotency_key=uid()));job=service.report(meeting['id'],store.meeting(meeting['id'])['transcript_revision'])
    for _ in range(300):
        if job['status'] in ('ready','error'):break
        await asyncio.sleep(.01)
    assert job['status']=='ready',job
    return service,provider,job,service.get_report(job['report_id'])

async def test_long_cross_maps_cancel_final_summary_and_preserve_history(store,meeting):
    apply(store,meeting,'Confirmed: deploy API-17 on Friday.',speaker='Client')
    filler='Ordinary discussion of observations, no decision or acceptance. '*8
    for n in range(320):
        text='Correction: confirmed deploy API-17 on Monday instead.' if n==160 else 'Cancel deploy API-17 because QA is not finished.' if n==319 else filler
        apply(store,meeting,text,segment=f'turn-{n}',seq=n+2,speaker='Client')
    service,provider,job,report=await generate(store,meeting)
    assert len(provider.calls)>5 and job['maps']==len(provider.calls)
    assert not report['payload']['decisions'] and 'cancelled' in report['payload']['summary_en']
    assert 'Friday' not in report['payload']['summary_en'] and 'Monday' not in report['payload']['summary_en']
    assert report['historical_payload']['open_questions'] and report['memory_snapshot'][0]['status']=='superseded'
    assert len(report['evidence_snapshot'])==321 and report['reconciliation']['history_validated']
    await service.shutdown();await service.retrieval.aclose()

async def test_report_edit_regenerate_preserves_versions_origin_and_evidence(store,meeting):
    apply(store,meeting,'I will review API-17 by 2026-10-22.')
    service,provider,job,first=await generate(store,meeting)
    payload=ReportPayload.model_validate(first['payload']);payload.action_items[0].owner='Alex';payload.action_items[0].raw_due_text='2026-10-25';payload.action_items[0].status='cancelled'
    saved=service.edit_report(first['id'],ReportEdit(expected_version=1,payload=payload,reviewed=True))
    assert saved['payload']['action_items'][0]['origin']=='user_edit' and saved['parent_id']==first['id']
    assert saved['edit_provenance']['changed_item_ids'] and saved['evidence_snapshot']==first['evidence_snapshot']
    next_job=service.report(meeting['id'],store.meeting(meeting['id'])['transcript_revision'])
    for _ in range(100):
        if next_job['status'] in ('ready','error'):break
        await asyncio.sleep(.01)
    assert next_job['status']=='ready',next_job
    assert service.get_report(saved['id'])['payload']==saved['payload']
    assert len(store.objects(meeting['id'],'reports'))==3
    with pytest.raises(AppError):service.edit_report(first['id'],ReportEdit(expected_version=1,payload=payload))
    await service.shutdown();await service.retrieval.aclose()

def test_owner_and_deadline_binding_does_not_cross_tasks(store,meeting):
    apply(store,meeting,'I will review API-17 by 2026-10-22; I will test API-71 by 2026-10-23.')
    payload=ReportPayload(action_items=[dict(id='wrong',text='I will review API-17.',text_en='',evidence_segment_ids=['s'],origin='transcript',confirmation='confirmed',owner='Minh',raw_due_text='2026-10-23')])
    with pytest.raises(AppError) as error:reconcile_report(payload,store.memory(meeting['id']),store.transcript(meeting['id']))
    assert error.value.code=='REPORT_MEMORY_DUE'

async def test_report_revision_warning_and_archive_unchanged_after_memory_edit(store,meeting):
    apply(store,meeting,'Confirmed: test API-17 in staging.',speaker='Client');service,_,_,report=await generate(store,meeting)
    old_snapshot=copy.deepcopy(report['memory_snapshot']);m=store.meeting(meeting['id']);db=store.db_for(m['id'])
    from app.meeting_memory import edit
    item=store.memory(m['id'])[0]
    with db:edit(db,m,item['id'],dict(status='cancelled'),item['version']);store.save_meeting(db,m)
    assert service.get_report(report['id'])['evidence_changed']
    assert service.get_report(report['id'])['memory_snapshot']==old_snapshot
    await service.shutdown();await service.retrieval.aclose()

async def test_demo_report_keeps_manual_cancel_as_user_edit_not_participant_fact(store,meeting):
    from app.meeting_memory import edit
    apply(store,meeting,'I will review API-71 by tomorrow.',segment='task')
    apply(store,meeting,'Confirmed: test API-17 in staging.',segment='decision',speaker='Client',seq=2)
    apply(store,meeting,'We have NOT approved test API-17 in staging.',segment='decision',revision=2,speaker='Client',seq=3)
    m=store.meeting(meeting['id']);db=store.db_for(m['id']);item=store.memory(m['id'])[0]
    with db:
        edit(db,m,item['id'],dict(text=item['text'],owner='Alex',raw_due_text='Maybe Friday',status='cancelled'),item['version']);m['demo']=True;store.save_meeting(db,m)
    service,_,_,report=await generate(store,m)
    assert not report['payload']['action_items'] and not report['payload']['decisions']
    assert report['memory_snapshot'][0]['origin']=='user_edit' and report['memory_snapshot'][0]['owner']=='Alex'
    await service.shutdown();await service.retrieval.aclose()

async def test_manual_owner_override_regeneration_is_labelled_not_recertified(store,meeting):
    from app.meeting_memory import edit
    apply(store,meeting,'I will review API-17.');m=store.meeting(meeting['id']);db=store.db_for(m['id']);item=store.memory(m['id'])[0]
    with db:edit(db,m,item['id'],dict(owner='Alex'),item['version']);store.save_meeting(db,m)
    service,_,_,report=await generate(store,m)
    assert not report['payload']['action_items'] and report['memory_snapshot'][0]['owner']=='Alex'
    assert report['memory_snapshot'][0]['origin']=='user_edit' and report['historical_payload']['open_questions']
    await service.shutdown();await service.retrieval.aclose()

async def test_report_summary_budget_fails_closed_without_cutting_or_extra_calls(store,meeting):
    for n in range(50):apply(store,meeting,'Ordinary discussion. '*45,segment=f'f{n}',seq=n+1)
    class LargeSummary(ReportProvider):
        async def complete(self,context,*args):
            self.calls.append(context);return ReportPayload(summary_en='Discussion. '*900,summary_segment_ids=[s['id'] for s in context['segments']])
    provider=LargeSummary();service=Service(store,Retrieval(store,Semantic(Path('.'))),provider);store.control(meeting['id'],dict(action='end',idempotency_key=uid()));job=service.report(meeting['id'],store.meeting(meeting['id'])['transcript_revision'])
    for _ in range(100):
        if job['status'] in ('ready','error'):break
        await asyncio.sleep(.01)
    assert job['status']=='error' and job['error']['code']=='REPORT_SUMMARY_BUDGET'
    assert len(provider.calls)==2 and not store.objects(meeting['id'],'reports')
    await service.shutdown();await service.retrieval.aclose()

def test_oversized_memory_clause_is_preserved_and_never_truncated_to_report(store,meeting):
    text='I will review API-17 '+('carefully '*500)+'.';apply(store,meeting,text)
    with pytest.raises(AppError) as error:reconcile_report(ReportPayload(),store.memory(meeting['id']),store.transcript(meeting['id']))
    assert error.value.code=='REPORT_CAPACITY' and store.evidence_revision(meeting['id'],'s',1)['text']==text

def test_user_edited_ai_proposal_has_provenance_without_relaxing_model_or_owner_guard(store,meeting):
    from app.llm import validate_report
    service=Service(store,Retrieval(store,Semantic(Path('.'))),None)
    payload=ReportPayload(ai_proposals=[dict(id='proposal',text='Consider caching.',evidence_segment_ids=[],origin='ai_proposal',confirmation='proposed')])
    first=service.save_report(meeting['id'],payload,0);draft=ReportPayload.model_validate(first['payload']);draft.ai_proposals[0].text='User alternative: consider indexing.'
    saved=service.edit_report(first['id'],ReportEdit(expected_version=1,payload=draft));item=saved['payload']['ai_proposals'][0]
    assert item['origin']=='user_edit' and 'proposal' in saved['edit_provenance']['changed_item_ids']
    manual=ReportPayload.model_validate(saved['payload']);validate_report(manual,[],user_edit=True)
    with pytest.raises(AppError) as error:validate_report(manual,[])
    assert error.value.code=='REPORT_ORIGIN'
    manual.ai_proposals[0].owner='Minh'
    with pytest.raises(AppError) as error:validate_report(manual,[],user_edit=True)
    assert error.value.code=='REPORT_PROPOSAL'
