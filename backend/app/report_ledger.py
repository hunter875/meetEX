"""Reconcile validated map output against the scoped evidence ledger, without another model."""
import copy
import re
from .models import ReportPayload,ReportItem
from .llm import SECTIONS,validate_report
from .meeting_memory import current,POLICY
from .errors import AppError

SECTION_KIND={'requirements':{'requirement'},'decisions':{'decision'},'action_items':{'action_item'},'open_questions':{'open_question','proposal','spoken_fact'}}
ACTIVE={'requirement':{'requested'},'decision':{'confirmed'},'action_item':{'accepted','completed'},'open_question':{'open'},'proposal':{'proposed'},'spoken_fact':{'stated'}}

def matches(item,ledger):
    ids=set(item.evidence_segment_ids);entities=set(re.findall(r'\b[A-Za-z]+-\d+\b',item.text+' '+item.text_en))
    return [m for m in ledger if any(e['segment_id'] in ids for e in m['evidence']) and (not entities or m['entity'] in entities)]

def reconcile_report(payload,ledger,segments):
    historical=ReportPayload();output=copy.deepcopy(payload);governed=0
    for section in SECTIONS:
        if section=='ai_proposals':continue
        kept=[]
        for item in getattr(output,section):
            linked=matches(item,ledger)
            if not linked:kept.append(item);continue
            valid=[m for m in linked if m['origin']=='transcript' and current(m) and m['status'] in ACTIVE[m['kind']] and m['kind'] in SECTION_KIND.get(section,set())]
            if not valid:
                getattr(historical,section).append(item);governed+=1;continue
            if item.owner and not any(m['owner']==item.owner for m in valid):raise AppError('REPORT_MEMORY_OWNER','Report owner does not match the accepted task evidence',502)
            if item.raw_due_text and not any(m['raw_due_text']==item.raw_due_text for m in valid):raise AppError('REPORT_MEMORY_DUE','Report deadline does not match this task',502)
            # A map paraphrase is retained as a draft, never used as proof of its
            # own current status. Rebuild governed sections from exact ledger clauses.
            getattr(historical,section).append(item);governed+=1
        setattr(output,section,kept)
    added=0
    for memory in ledger:
        if not current(memory) or memory['origin']!='transcript' or memory['status'] not in ACTIVE.get(memory['kind'],set()):continue
        section=next((s for s,kinds in SECTION_KIND.items() if memory['kind'] in kinds),'open_questions')
        if any(memory in matches(item,ledger) for item in getattr(output,section)):continue
        if len(memory['text'])>4000:raise AppError('REPORT_CAPACITY','Whole memory clause exceeds report item budget; transcript preserved, no truncated item published',422)
        confirmed=memory['status'] in ('confirmed','accepted','completed')
        item=ReportItem(id='memory-'+memory['id'],text=memory['text'],text_en=memory['text'],evidence_segment_ids=list(dict.fromkeys(e['segment_id'] for e in memory['evidence'])),origin='transcript',confirmation='confirmed' if confirmed else 'unconfirmed',owner=memory['owner'] if confirmed else None,raw_due_text=memory['raw_due_text'] if confirmed else None,normalized_due=memory['normalized_due'] if memory['due_rule']=='iso-date' else None,status=memory['status'])
        # Exact raw evidence must still pass the original report guards. Unsupported
        # extraction grammar cannot silently weaken validation to force publication.
        validate_report(ReportPayload(**{section:[item]}),segments,check_coverage=False)
        getattr(output,section).append(item);added+=1
    stateful=[m for m in ledger if m['kind'] in ('decision','action_item','requirement','proposal')]
    if stateful:
        historical.summary_vi=payload.summary_vi;historical.summary_en=payload.summary_en;historical.summary_segment_ids=payload.summary_segment_ids
        lines=[];summary_ids=[]
        for m in stateful:
            if not current(m) or m['origin']!='transcript':continue
            if m['status']=='disputed':text=f'{m["entity"] or "Item"} {m.get("environment") or ""}: disputed; clarification required.'
            elif m['status'] in ('cancelled','unconfirmed','requested','proposed'):text=f'{m["entity"] or "Item"} {m.get("environment") or ""}: {m["action"] or m["kind"]} {m["status"]}; check evidence and clarify if unresolved.'
            else:text=f'[{m["kind"]}/{m["status"]}] '+m['text']
            if len('\n'.join(lines+[text]))>14000:raise AppError('REPORT_CAPACITY','Current ledger summary exceeds report budget; no partial summary published',422)
            lines.append(text);summary_ids.extend(e['segment_id'] for e in m['evidence'])
        output.summary_en='\n'.join(lines) or 'Which decisions and tasks still need clarification?'
        state_vi={'confirmed':'đã xác nhận','accepted':'đã nhận','completed':'đã báo hoàn thành','cancelled':'đã hủy','disputed':'mâu thuẫn, cần làm rõ','unconfirmed':'chưa xác nhận','requested':'được yêu cầu, chưa nhận','proposed':'đề xuất, chưa chốt'}
        vi=[]
        for m in stateful:
            if not current(m) or m['origin']!='transcript':continue
            state=state_vi.get(m['status'],m['status'])
            if m['status'] in ('confirmed','accepted','completed'):line=f'Nguyên văn ({state}): '+m['text']
            elif m['status'] in ('unconfirmed','disputed','requested','proposed'):line=f'Cần làm rõ {m["action"] or m["kind"]} {m["entity"] or "đối tượng chưa rõ"} {m.get("environment") or ""} ({state})?'
            else:line=f'{m["entity"] or "Mục chưa rõ đối tượng"} {m.get("environment") or ""}: {m["action"] or m["kind"]} — {state}.'
            vi.append(line)
        output.summary_vi='\n'.join(vi) or 'Cần làm rõ những quyết định và công việc nào?'
        if len(output.summary_vi)>15000:raise AppError('REPORT_CAPACITY','Vietnamese ledger summary exceeds budget',422)
        output.summary_segment_ids=list(dict.fromkeys(summary_ids)) or payload.summary_segment_ids
        output.capture_warnings.append('Tổng quan trạng thái được dựng từ grammar memory có giới hạn; map summary gốc nằm trong lịch sử, không là nguồn sự thật.')
    # Coverage includes validated historical speech. Current and historical portions
    # remain separately labelled in export; old commitments must not disappear.
    joint=copy.deepcopy(output)
    for section in SECTIONS:getattr(joint,section).extend(getattr(historical,section))
    validate_report(joint,segments)
    for section,kinds in SECTION_KIND.items():
        if section not in ('decisions','action_items'):continue
        for item in getattr(output,section):
            linked=[m for m in matches(item,ledger) if m['kind'] in kinds]
            if linked and not any(current(m) and m['status'] in ACTIVE[m['kind']] for m in linked):raise AppError('REPORT_MEMORY_STATE','Historical decision leaked into current report',502)
    if any(m['origin']=='user_edit' for m in ledger):output.capture_warnings.append('Ghi chú/chỉnh sửa memory của bạn chỉ ở memory snapshot có nhãn user_edit; không được tái chứng nhận là participant đã nói.')
    return output,historical,dict(policy=POLICY,removed_from_current=governed,added_from_evidence=added,user_edit_memory_items=sum(m['origin']=='user_edit' for m in ledger),history_validated=True,scope='bounded explicit grammar; other map items retain original validators, not general entailment')
