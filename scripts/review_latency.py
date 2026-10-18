"""Review saved, billed latency trials without invoking a provider."""
from pathlib import Path
import json
import math
import re
import statistics
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.llm import validate_suggestion
from app.models import SuggestionPayload
from app.errors import AppError
E=ROOT/'docs/evidence'
run=json.loads((E/'speed-repeat.json').read_text('utf8'))
specs=json.loads((ROOT/'fixtures/speed-scenarios.json').read_text('utf8'))
baseline=json.loads((E/'extended-live-review.json').read_text('utf8'))
by_name={c['name']:c for c in run['cases']}
rows=[]
for spec in specs:
    c=by_name.get(spec['name'],{});suggestion=(c.get('suggestions') or [{}])[0]
    p=suggestion.get('payload',{});snapshot=suggestion.get('snapshot',{})
    checks={'ready':c.get('request_status')=='ready','not_stale':suggestion.get('stale') is False}
    try:validate_suggestion(SuggestionPayload(**p),snapshot);checks['full_validation']=True
    except (AppError,ValueError,KeyError):checks['full_validation']=False
    value=json.dumps(p,ensure_ascii=False).casefold();reply=p.get('reply_en','').casefold();a=spec.get('assertions',{})
    if a.get('payload_contains'):checks['expected_values']=all(v.casefold() in value for v in a['payload_contains'])
    if a.get('forbid_reply'):checks['no_injected_or_wrong_reply']=not any(v.casefold() in reply for v in a['forbid_reply'])
    if a.get('project_scope'):
        checks['project_scope']=all(s['project_id']==snapshot['project_id'] for s in snapshot['sources'])
        checks['no_foreign_canary']=a['foreign_canary'].casefold() not in json.dumps([p,snapshot],ensure_ascii=False).casefold()
    if a.get('deployment_unknown'):checks['deployment_unknown']=bool(re.search(r'unknown|not confirmed|unconfirmed|chưa rõ|chưa được xác nhận',value))
    name=spec['name']
    if name=='ambiguous-we-owner':checks['no_unaccepted_volunteering']=not bool(re.search(r"\bi\s+(?:will|can\s+(?:look|own|take|investigate))\b|\bi'll\b",reply))
    if name=='confirmed-relative-date':checks['relative_due']=('tomorrow' in reply or 'ngày mai' in value) and '10:00' in value
    if name=='deadline-replaced':checks['replacement_due']='2026-10-22' in value and ('cancel' in value or 'hủy' in value)
    if name=='confirmed-owner-transfer':checks['new_owner']='priya' in value and not bool(re.search(r'\bi\s+(?:will|can)\s+own',reply))
    if name=='long-report-start-middle-tail':checks['latest_requirement']='bom' in value and 's43' in p.get('supporting_segment_ids',[])
    if name=='regression-negative-deployment':checks['negation_retained']='không' in p.get('meaning_vi','').lower() and reply.endswith('?')
    if name=='regression-missing-status':checks['missing_status']=p.get('evidence_status')=='missing' and reply.endswith('?')
    if name=='regression-conflicting-api17':checks['both_conflicting_sources']=p.get('evidence_status')=='conflicting' and all(code in value for code in ('401','403')) and len({id for f in p.get('findings',[]) for id in f['source_ids']})>=2
    rows.append(dict(name=name,status='PASS' if all(checks.values()) else 'FAIL',checks=checks,duration_ms=suggestion.get('duration_ms')))

def stats(values):
    values=sorted(values)
    return dict(n=len(values),min_s=values[0]/1000,median_s=statistics.median(values)/1000,
                p95_s=values[math.ceil(len(values)*.95)-1]/1000,max_s=values[-1]/1000,
                at_most_1_5s=sum(v<=1500 for v in values))
durations=[r['duration_ms'] for r in rows if r['duration_ms'] is not None]
matched=stats([r['duration_ms'] for r in rows if not r['name'].startswith('regression-') and r['duration_ms'] is not None])
all_stats=stats(durations)
phases=[]
for file,label in [('speed-pooled.json','Shared HTTP client'),('speed-compact.json','Compact live prompt'),('speed-aliased.json','Short IDs (incomplete harness run)'),('speed-final.json','Short outputs, before targeted correction'),('speed-repeat.json','Final verified profile')]:
    path=E/file
    if not path.exists():continue
    trial=json.loads(path.read_text('utf8'));ds=[c['suggestions'][0]['duration_ms'] for c in trial['cases'] if c.get('suggestions')]
    phases.append(dict(file=file,label=label,observed_cases=len(trial['cases']),accepted=len(ds),failed=sum(c.get('request_status')=='error' for c in trial['cases']),stats=stats(ds) if ds else None))
metrics=dict(matched_ten=matched,all_sixteen=all_stats,
             baseline_ten_median_s=baseline['metrics']['suggestion_median_s'],
             matched_median_reduction_pct=100*(1-matched['median_s']/baseline['metrics']['suggestion_median_s']),
             target_seconds=1.5,matched_median_target_met=matched['median_s']<=1.5,
             all_sixteen_median_target_met=all_stats['median_s']<=1.5,
             every_request_target_met=all_stats['max_s']<=1.5)
review=dict(result='PASS' if len(rows)==16 and all(r['status']=='PASS' for r in rows) else 'FAIL',
            scope='Complete validated backend suggestions, warm pooled connection after a real connection test; no application-response-cache hits; provider prefix caching remains enabled. Does not measure speech-to-UI or cold-first-suggestion latency.',
            synthetic_input=True,provider_mode='real',meet_dom_tested=False,source_file='speed-repeat.json',source_hashes=run.get('source_hashes'),cases=rows,metrics=metrics,phases=phases,
            credential_cleared=run.get('credential_cleared'),
            quality_scope='Schema/evidence guards and stated fixture checks plus Codex output inspection; not independent human review or a general semantic-accuracy guarantee.')
(E/'speed-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
lines=['# Tối ưu thời gian gợi ý hoàn chỉnh','',
 '**Kết quả thực đo: khoảng 1,5 giây trung vị; chưa bảo đảm mọi request ≤1,5 giây.** DeepSeek `deepseek-flash` thật, dữ liệu synthetic. Giữ bước parse JSON, đổi alias về ID gốc, kiểm tra evidence/negation/role/commitment rồi mới publish; không hiển thị token chưa kiểm tra.',
 '', '| Phép đo | Trước | Sau |', '| --- | --- | --- |',
 f'| Cùng 10 kịch bản mở rộng: median | {metrics["baseline_ten_median_s"]:.3f} s | {matched["median_s"]:.3f} s |',
 f'| 16 kịch bản cuối: median | — | {all_stats["median_s"]:.3f} s |',
 f'| 16 kịch bản: min / p95 mẫu / max | — | {all_stats["min_s"]:.3f} / {all_stats["p95_s"]:.3f} / {all_stats["max_s"]:.3f} s |',
 f'| Request ≤1,5 s trong 16 mẫu | — | {all_stats["at_most_1_5s"]}/16 |',
 '', f'Median trên bộ 10 mẫu tương ứng giảm {metrics["matched_median_reduction_pct"]:.1f}%. So sánh lịch sử cùng fixture, không phải thí nghiệm mạng đồng thời. n nhỏ và có biến động provider/mạng; p95 mẫu không phải SLA.',
 '', '## Đã thay đổi', '',
 '- Dùng lại AsyncClient/connection pool, keepalive 60 s khi server cho phép; đóng pool khi backend shutdown. Mỗi request dùng credential hiện tại, không giữ Authorization trong client mặc định.',
 '- Live dùng hướng dẫn ngắn và một câu trả lời dễ nói; action explain/ask vẫn có thể giải thích theo yêu cầu. Report vẫn giữ pipeline/schema đầy đủ.',
 '- Chỉ bỏ metadata vận chuyển/lưu trữ khỏi prompt live; giữ nguyên lời thoại, memory, glossary, nội dung nguồn và cờ stale. Snapshot đầy đủ/citation metadata vẫn lưu như trước.',
 '- Dùng ID C1/T1 trong request thay cho UUID dài. Backend đổi về đúng ID gốc; alias lạ bị chặn và không lẫn mapping giữa các request.',
 '- Ưu tiên turn mới nhất; sửa lỗi theo đúng loại lỗi, tối đa một lượt. Không tăng số lần retry lỗi auth/timeout/JSON sai để đạt số đo đẹp.',
 '', '## Phạm vi thời gian', '',
 'Đo thời gian tạo và kiểm tra gợi ý tại backend, gồm lượt sửa nếu có. Connection test làm ấm client trước corpus; request đầu lạnh chưa được chứng minh ở 1,5 giây. Không dùng cache câu trả lời của ứng dụng để tạo số đo, nhưng prefix cache của provider vẫn hoạt động.',
 '', 'Auto vẫn giữ stable khoảng 1 s và debounce 2 s theo cấu hình hiện tại. Vì thế 1,5 s ở đây không phải từ lúc người khác bắt đầu nói hoặc từ khi phụ đề đang đổi tới UI. Meet thật, cold start, corpus lớn và mạng chậm vẫn cần đo riêng.',
 '', '## Giữ lại các lượt thử chưa đạt', '', '| Bước | Số case quan sát | Gợi ý được chấp nhận | Lỗi | Median của gợi ý được chấp nhận |', '| --- | --- | --- | --- | --- |']
for phase in phases:
    s=phase['stats'];median=f'{s["median_s"]:.3f} s' if s else '—'
    lines.append(f'| {phase["label"]} | {phase["observed_cases"]} | {phase["accepted"]} | {phase["failed"]} | {median} |')
lines+=['', 'Lượt short-ID đầu bị lỗi ghi evidence trên Windows ở case thứ 9; file cuối vẫn giữ chín kết quả và credential đã được xóa. Harness chuyển sang ghi file tạm + replace có lock/retry. Lượt trước final có một kết quả bị role guard chặn; không tính nó thành thành công và không bỏ guard. Lượt cuối có đủ 16/16 gợi ý được chấp nhận.',
 '', '## Kết quả từng case cuối', '', '| Case | Check | Hoàn chỉnh |', '| --- | --- | --- |']
for r in rows:lines.append(f'| {r["name"]} | {r["status"]} | {r["duration_ms"]/1000:.3f} s |')
lines+=['', '[JSON có guards/checks/source hashes](evidence/speed-review.json) · [Evidence lượt cuối](evidence/speed-repeat.json) · [Fixture 16 mẫu](../fixtures/speed-scenarios.json)',
 '', 'Các test mới kiểm tra reuse/fresh credential/close pool, hủy stream, round-trip alias/scope, giữ evidence khi rút prompt và không retry thêm timeout/auth/bad JSON. Semantic guard vẫn chỉ bao phủ một số mẫu ngôn ngữ; cần đối chiếu nội dung quan trọng trước khi dùng.']
(ROOT/'docs/LATENCY_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print(json.dumps(dict(result=review['result'],metrics=metrics,failed=[r['name'] for r in rows if r['status']=='FAIL'])))
