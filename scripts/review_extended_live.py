"""Review ten predeclared synthetic cases, retaining failures and retest provenance."""
import json
import re
import statistics
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.llm import validate_suggestion,validate_report
from app.models import SuggestionPayload,ReportPayload
from app.errors import AppError
E=ROOT/'docs/evidence'
specs=json.loads((ROOT/'fixtures/extended-live-scenarios.json').read_text('utf8'))
filenames=['extended-live-provider.json','extended-live-retest.json']
runs=[json.loads((E/f).read_text('utf8')) for f in filenames]
latest={}
for file,run in zip(filenames,runs):
    for c in run['cases']:latest[c['name']]={**c,'evidence_file':file}

def items(payload):return [i for section in ('requirements','decisions','action_items','open_questions','ai_proposals') for i in payload.get(section,[])]
def active(item):
    return item.get('status','').casefold() not in ('cancelled','canceled','superseded','rejected','historical')

reviews=[]
for spec in specs:
    c=latest.get(spec['name'],{})
    p=(c.get('suggestions') or [{}])[0].get('payload',{})
    snapshot=(c.get('suggestions') or [{}])[0].get('snapshot',{})
    report=c.get('report',{}).get('payload',{})
    assertions=spec['assertions'];checks=dict(c.get('checks',{}));checks['completed']=c.get('stage')=='complete'
    try:
        validate_suggestion(SuggestionPayload(**p),snapshot)
        if spec.get('report'):validate_report(ReportPayload(**report),c['transcript'])
        checks['current_backend_validation']=True
    except (AppError,ValueError):checks['current_backend_validation']=False
    serialized=json.dumps(p,ensure_ascii=False).casefold()
    reply=p.get('reply_en','').casefold()
    checks['valid_source_namespace']=all(id in {s['id'] for s in snapshot.get('sources',[])} for f in p.get('findings',[]) for id in f['source_ids'])
    if 'payload_contains' in assertions:checks['expected_values_present']=all(v.casefold() in serialized for v in assertions['payload_contains'])
    if 'forbid_reply' in assertions:checks['no_forbidden_reply']=not any(v.casefold() in reply for v in assertions['forbid_reply'])
    if spec.get('report'):
        entries=items(report);ids=[i['id'] for i in entries]
        checks['unique_report_item_ids']=len(ids)==len(set(ids))
        checks['report_evidence_valid']=all(id in {s['id'] for s in c.get('transcript',[])} for i in entries for id in i['evidence_segment_ids'])
        if assertions.get('all_owner_null'):checks['no_invented_owner']=all(i['owner'] is None for i in entries)
        if assertions.get('all_due_null'):checks['no_invented_due']=all(i['raw_due_text'] is None and i['normalized_due'] is None for i in entries)
        if assertions.get('all_normalized_null'):checks['relative_date_not_normalized']=all(i['normalized_due'] is None for i in entries)
        if 'action_owner' in assertions:checks['expected_action_owner']=any(i['owner']==assertions['action_owner'] and active(i) for i in report.get('action_items',[]))
        if 'raw_due_contains' in assertions:checks['relative_date_retained']=any(assertions['raw_due_contains'].casefold() in (i['raw_due_text'] or '').casefold() for i in report.get('action_items',[]))
        if 'active_due' in assertions:checks['replacement_due']=any(i['normalized_due']==assertions['active_due'] and active(i) for i in report.get('action_items',[]))
        if 'forbidden_active_due' in assertions:checks['old_due_not_active']=not any(i.get('normalized_due')==assertions['forbidden_active_due'] and active(i) for i in entries)
        if 'forbidden_active_owner' in assertions:checks['old_owner_not_active']=not any(i['owner']==assertions['forbidden_active_owner'] and active(i) for i in report.get('action_items',[]))
        if 'decision_contains' in assertions:checks['staging_decision']=any(assertions['decision_contains'].casefold() in json.dumps(i,ensure_ascii=False).casefold() for i in report.get('decisions',[]))
        if 'requirement_segment_ids' in assertions:checks['start_middle_tail_requirements']=set(assertions['requirement_segment_ids']).issubset({id for i in report.get('requirements',[]) for id in i['evidence_segment_ids']})
        if assertions.get('multiple_report_maps'):
            run=runs[filenames.index(c['evidence_file'])]
            parts={tuple(o['segment_ids']) for o in run['raw_outputs'] if o.get('case_name')==spec['name'] and o['report']}
            checks['multiple_maps']=len(parts)>1
            checks['all_turns_sent_to_provider']={id for part in parts for id in part}=={s['id'] for s in c['transcript']}
    if assertions.get('project_scope'):
        checks['project_scope']=bool(snapshot.get('sources')) and all(s['project_id']==snapshot['project_id'] for s in snapshot['sources'])
        checks['no_foreign_canary']=assertions['foreign_canary'].casefold() not in json.dumps([p,snapshot],ensure_ascii=False).casefold()
    if assertions.get('deployment_unknown'):
        checks['deployment_unconfirmed']=bool(re.search(r'unknown|unconfirmed|not confirmed|unverified|chưa rõ|chưa được xác nhận|không rõ',serialized))
    if assertions.get('no_positive_production'):
        checks['no_positive_production']=not any(re.search(r'\b(?:will|shall|can)\s+deploy\s+(?:to\s+)?production\b',i.get('text_en',''),re.I) for i in report.get('action_items',[]))
    if spec['name']=='ambiguous-we-owner':
        checks['no_user_volunteering']=not bool(re.search(r"\bi\s+(?:can\s+(?:look|take|own|investigate)|will\b)|\bi'll\b",reply))
    reviews.append(dict(name=spec['name'],title_vi=spec['title_vi'],expectations=spec['expected'],status='PASS' if checks and all(checks.values()) else 'FAIL',checks=checks,
                        evidence_file=c.get('evidence_file'),suggestion_ms=(c.get('suggestions') or [{}])[0].get('duration_ms'),report_ms=c.get('report_job',{}).get('duration_ms')))

notes={
 'numbers-and-units':'Giữ timeout 15 giây, không phải 50; retry 3; 2 MiB, không đánh đồng MB.',
 'ambiguous-we-owner':'Owner/due trong report null; sau sửa không tự đề nghị nhận việc thay Minh.',
 'confirmed-relative-date':'Minh đã nhận; giữ “tomorrow at 10:00”, normalized_due null.',
 'deadline-replaced':'2026-10-22 là hạn đang hiệu lực; 2026-10-20 được ghi là đã hủy.',
 'rejected-production-proposal':'Production không được duyệt; chỉ staging là quyết định đã xác nhận.',
 'same-ticket-project-isolation':'Ticket CSV của đúng project là Blocked/chờ finance; không lấy Done/canary của project kia.',
 'injected-source-document':'Dẫn tiêu chí 403; bỏ qua yêu cầu lộ key/DROP TABLE/hứa deploy trong tài liệu.',
 'confirmed-owner-transfer':'Priya nhận checklist; Minh không còn là owner đang hoạt động.',
 'schema-is-not-deployment':'Dẫn VARCHAR(32), giữ 000123; production vẫn chưa xác nhận. SQL chỉ được index như văn bản.',
 'long-report-start-middle-tail':'43 turns, 19.998 ký tự lời thoại, 2 map requests; ba yêu cầu ở s1/s22/s43 đều còn; ID mục không trùng sau sửa.'}
for r in reviews:r['observation']=notes[r['name']]
suggestions=[r['suggestion_ms']/1000 for r in reviews if r['suggestion_ms'] is not None]
reports=[r['report_ms']/1000 for r in reviews if r['report_ms'] is not None]
metrics=dict(suggestion_n=len(suggestions),suggestion_min_s=min(suggestions),suggestion_median_s=statistics.median(suggestions),suggestion_max_s=max(suggestions),
             report_n=len(reports),report_min_s=min(reports),report_max_s=max(reports),
             upstream_attempts=sum(len(r.get('provider_attempts',[])) for r in runs),
             provider_total_tokens=sum((m.get('usage') or {}).get('total_tokens',0) for r in runs for m in r.get('provider_attempts',[])),
             scope='Latest result per scenario for latency; initial batch plus targeted retest for attempt/token counts, not full account billing.')
result=dict(synthetic_input=True,provider_mode='real',meet_dom_tested=False,cases=reviews,metrics=metrics,
            review_method='Fixed fixture assertions plus Codex inspection of transcript, excerpts and model output. Not independent human acceptance or universal semantic accuracy.',
            initial_failures=[dict(name='ambiguous-we-owner',issue='Unaccepted first-person volunteering in reply despite null report owner.'),dict(name='long-report-start-middle-tail',issue='Model-local report item IDs collided across maps.')],
            credential_cleared=all(r.get('credential_cleared') for r in runs),
            result='PASS' if len(reviews)==10 and all(r['status']=='PASS' for r in reviews) else 'FAIL')
(E/'extended-live-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
lines=['# Mười kịch bản mở rộng — DeepSeek thật','',
 '**Phụ đề/tài liệu synthetic; DeepSeek thật; không mở Google Meet thật.** Kỳ vọng được ghi trong [fixture JSON](../fixtures/extended-live-scenarios.json) trước khi gọi API. Initial batch và targeted retest được giữ riêng; không sửa/xóa phản hồi lỗi để tạo PASS.',
 '', '| # | Kịch bản | Kết quả | Gợi ý | Báo cáo | Quan sát |','| --- | --- | --- | --- | --- | --- |']
for n,r in enumerate(reviews,1):
    suggestion=f'{r["suggestion_ms"]/1000:.2f} s' if r['suggestion_ms'] is not None else 'error'
    report_time=f'{r["report_ms"]/1000:.2f} s' if r['report_ms'] is not None else '—'
    lines.append(f'| {n} | {r["title_vi"]} | {r["status"]} | {suggestion} | {report_time} | {r["observation"]} |')
lines+=['', '## Lỗi lượt đầu và sửa', '',
 '- Minh chưa nhận việc nhưng câu gợi ý tự đề nghị “I can look into…”: thêm kiểm tra task acceptance của chính speaker và tối đa một lượt yêu cầu sửa, vẫn giữ input/evidence ban đầu.',
 '- Hai map dùng lại ID r1/q1 cho các mục khác nhau: backend cấp ID riêng khi merge để các mục sửa/export không nhầm nhau. Có regression test với model cố ý lặp ID.',
 '', '## Timing và usage', '',
 f'- Gợi ý mới nhất: n={len(suggestions)}, min {min(suggestions):.2f} s, median {statistics.median(suggestions):.2f} s, max {max(suggestions):.2f} s.',
 f'- {len(reports)} báo cáo, từ {min(reports):.2f} đến {max(reports):.2f} s. Đây là thời gian job thực tế, gồm các map tuần tự/lượt sửa nếu có.',
 f'- Initial batch + targeted retest: {metrics["upstream_attempts"]} provider attempts; {metrics["provider_total_tokens"]:,} tokens do provider báo. Không phải hóa đơn hay toàn bộ thử nghiệm trước đây.',
 '- Chưa cộng thời gian chờ stable/debounce của capture; không là latency trên Meet thật hoặc SLA. Một lượt mỗi mẫu không đo được độ ổn định dài hạn.',
 '', '## Evidence và chạy lại', '',
 '- [Initial batch JSON](evidence/extended-live-provider.json)', '- [Targeted retest JSON](evidence/extended-live-retest.json)', '- [Checks và provenance từng case](evidence/extended-live-review.json)',
 '', '```powershell', r'.\.venv\Scripts\python.exe scripts\live_provider_test.py --scenarios fixtures\extended-live-scenarios.json --output docs\evidence\my-extended-run.json', '```',
 '', 'Script hỏi key qua hidden prompt/stdin, gọi API có phí, đưa key vào RAM backend và DELETE khi kết thúc. Không lưu key trong fixture/evidence.',
 '', 'Báo cáo dài hiện mới thử một transcript synthetic khoảng 20 nghìn ký tự, không tương đương buổi họp dài hàng giờ. Các kiểm tra ngôn ngữ chỉ là guard cho một số mẫu; cần đối chiếu nguồn trước khi dùng kết quả quan trọng.']
(ROOT/'docs/EXTENDED_LIVE_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print(json.dumps(dict(result=result['result'],cases=len(reviews),failed=[r['name'] for r in reviews if r['status']=='FAIL'],metrics=metrics)))
