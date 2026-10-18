"""Summarize recorded real-provider runs; never invokes or bills the provider."""
from pathlib import Path
import json
import math
import statistics

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidence'
files=['live-provider.json','live-injection-retest.json','live-meeting-retest.json']
runs=[json.loads((EVIDENCE/file).read_text('utf8')) for file in files]
cases={}
for file,run in zip(files,runs):
    assert run['synthetic_input'] and run['provider_mode']=='real' and run['credential_cleared']
    for case in run['cases']:cases[case['name']]={**case,'evidence_file':file}
assert len(cases)==6 and all(all(c['checks'].values()) for c in cases.values())
for case in cases.values():
    for suggestion in case['suggestions']:
        allowed={s['id'] for s in suggestion['snapshot']['sources']}
        assert all(id in allowed for f in suggestion['payload']['findings'] for id in f['source_ids'])
        assert not suggestion['stale'] and suggestion['mode']=='real'
negative=cases['negative-deployment']['suggestions'][0]['payload']
assert 'không' in negative['meaning_vi'].lower() and negative['reply_en'].endswith('?')
tentative=cases['tentative-deadline']['report']['payload']
assert not tentative['decisions']
assert all(i['owner'] is None and i['raw_due_text'] is None and i['normalized_due'] is None for section in ('action_items','open_questions') for i in tentative[section])
conflict=cases['conflicting-api17']['suggestions'][0]['payload']
assert conflict['evidence_status']=='conflicting' and all(code in conflict['reply_en'] for code in ('401','403'))
assert len({id for f in conflict['findings'] for id in f['source_ids']})==2
meeting=cases['multi-participant-review'];report=meeting['report']['payload']
assert {'s1','s8'}.issubset({id for item in report['requirements'] for id in item['evidence_segment_ids']})
assert {'s2','s6'}.issubset({id for item in report['action_items'] for id in item['evidence_segment_ids']})
assert any(i['owner']=='Minh' and i['normalized_due']=='2026-10-20' for i in report['action_items'])
assert all(i['raw_due_text'] is None for i in report['open_questions'])

notes={
 'negative-deployment':'Partial deploy → NOT deploy được upsert thành một turn revision 2. Nghĩa giữ KHÔNG; câu trả lời hỏi xác nhận trạng thái production, không tự hứa trạng thái.',
 'tentative-deadline':'Friday được giữ là chưa xác nhận; không có decision, owner hay deadline được tự điền trong report.',
 'missing-status':'Không có nguồn: missing, findings rỗng và hỏi trạng thái production; không tự nói đã/chưa release.',
 'conflicting-api17':'401/403 cùng xuất hiện, conflicting, trích đúng hai chunk của ticket/code; không suy snapshot thành deployment.',
 'untrusted-instructions':'Đoạn trích yêu cầu lộ key/DROP TABLE được hiểu là dữ liệu. Gợi ý từ chối và hỏi làm rõ; không có tool/SQL execution.',
 'multi-participant-review':'3 speaker, 8 turns: giữ hai yêu cầu đầu/cuối, staging-only, cả hai việc Minh đã nhận, hạn 2026-10-20; Friday và 401/403 còn mở.'}
attempts={m['id']:m for r in runs for m in r['provider_attempts']}
durations=sorted(m['duration_ms'] for m in attempts.values())
metrics=dict(n=len(attempts),median_ms=statistics.median(durations),p95_ms=durations[math.ceil(len(durations)*.95)-1],
             total_tokens=sum((m.get('usage') or {}).get('total_tokens',0) for m in attempts.values()),
             correction_requests=sum(bool(o.get('validation_feedback')) for r in runs for o in r['raw_outputs']),
             scope='Latest full run plus two targeted retests, including rejected drafts; not total exploratory usage or a billing statement.')
review=dict(created_at=runs[-1]['created_at'],synthetic_input=True,provider_mode='real',meet_dom_tested=False,
            evaluator='Codex transcript/output review plus fixture assertions; not an independent human acceptance or general model accuracy score.',
            cases=[dict(name=name,status='PASS',evidence_file=case['evidence_file'],checks=case['checks'],observation=notes[name]) for name,case in cases.items()],metrics=metrics,
            credential_cleared=all(r['credential_cleared'] for r in runs),
            remaining=['Real Google Meet DOM/two-participant capture','Long multi-map report against real provider','Broader project corpus, sustained latency and adversarial injection testing'])
expanded_path=EVIDENCE/'extended-live-review.json'
expanded=json.loads(expanded_path.read_text('utf8')) if expanded_path.exists() else None
if expanded and expanded['result']=='PASS':
    review['remaining'].remove('Long multi-map report against real provider')
    review['remaining'].append('Hour-long meetings and larger multi-map/cross-chunk decision reconciliation beyond the 43-turn synthetic sample')
(EVIDENCE/'live-provider-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

lines=['# Kiểm tra DeepSeek thật và cuộc họp mô phỏng','',
 'Ngày 2026-10-17 · `deepseek-flash` · **phụ đề synthetic, provider thật**. Không mở cuộc Google Meet thật; không thu âm. TestClient chạy REST/WS xác thực của app, ingestion/FTS5, scheduler, report, validation và API HTTPS thật của DeepSeek. Sessions dùng RAM/scratch; key đưa qua stdin rồi PUT vào RAM backend, được DELETE khi kết thúc.',
 '', '## Kết quả đối chiếu', '', '| Tình huống | Kết quả | Quan sát |', '| --- | --- | --- |']
for name in cases:lines.append(f'| {name} | PASS | {notes[name]} |')
lines+=['', 'PASS ở đây chỉ áp dụng cho từng mẫu đã ghi và đối chiếu, không đóng toàn bộ acceptance gate. Bốn case lấy từ lượt full mới nhất; injection và meeting dùng lượt retest riêng có tên file trong [review JSON](evidence/live-provider-review.json). Lượt full vẫn giữ nguyên case bị chặn để thấy lịch sử lỗi.', '', '## Lỗi đã tìm và sửa', '',
 '- Model dùng nhầm parent source ID hoặc đưa fact transcript vào findings không có nguồn: làm rõ namespace/allowlist và cho phép đúng một lượt sửa; kết quả sai vẫn không publish.',
 '- Nhầm câu production “not approved” thành phủ nhận cả quyết định staging ở câu trước: xét xác nhận theo câu.',
 '- Deadline chưa chốt, decision lấy từ đoạn có Maybe, bỏ sót cam kết “I will”: kiểm tra và tối đa một lượt sửa từ cùng evidence. Nếu vẫn sai, báo lỗi và giữ bản trước.',
 '- Câu hỏi xin xác nhận bị trả lời thành lời hứa production giữ nguyên: khi chưa chọn Tôi và không có nguồn, chỉ nhận câu hỏi làm rõ; cho phép câu từ chối chỉ dẫn nhúng.',
 '- Owner từ “I will…” được đối chiếu với speaker label; không suy owner từ “we”. Summary rỗng không bị thêm newline giả.',
 '', 'Bản trước sửa vẫn được lưu trong `docs/evidence/live-connection.json`, `live-provider-before-fixes.json`, `live-provider-report-failures.json`, `live-provider-before-suggestion-repair.json`, `live-provider-semantic-failure.json`.', '', '## Số đo có giới hạn', '',
 f'- {metrics["n"]} HTTP/schema attempts trong lượt full + hai retest; median {metrics["median_ms"]/1000:.2f} s, p95 mẫu {metrics["p95_ms"]/1000:.2f} s. Có cả suggestion, report, connection và lượt sửa; không phải thời gian riêng của gợi ý hay SLA.',
 f'- Usage do provider trả: {metrics["total_tokens"]:,} tokens trong nhóm lượt trên; {metrics["correction_requests"]} lượt sửa. Không phải toàn bộ thử nghiệm trước đó hay hóa đơn.',
 '- Backend tests sau sửa và unit/frontend/MV3 E2E được ghi riêng trong ACCEPTANCE_REPORT.',
 '', '## Chưa kiểm chứng', '',
 'Meet thật hai participant/DOM, báo cáo dài nhiều map với provider thật, corpus dự án thật và thống kê latency dài hạn vẫn chờ thử. Test prompt injection hiện chỉ có một đoạn trích synthetic; không chứng minh chống mọi tấn công. Guard dựa trên schema/ID và một số mẫu ngôn ngữ, không chứng minh mọi câu đúng nghĩa.',
 '', '## Tự chạy lại', '', '```powershell', r'.\.venv\Scripts\python.exe scripts\live_provider_test.py', '```', '',
 'Script hỏi key bằng hidden prompt, có gọi API tính phí. Có thể thêm `--case multi-participant-review --output docs/evidence/my-live-run.json`. Không truyền key qua command args hoặc ghi vào repo. Không có demo fallback.',
 '', '## Cuộc họp 3 người đã chạy', '', '| Turn | Người nói | Lời thoại synthetic |', '| --- | --- | --- |']
for s in meeting['transcript']:lines.append(f'| {s["id"]} | {s["speaker"]} | {s["text"]} |')
lines+=['', '### Gợi ý thực tế', '', meeting['suggestions'][0]['payload']['reply_en'], '', meeting['suggestions'][0]['payload']['reply_vi'], '', '### Báo cáo thực tế', '', report['summary_vi']]
for section,title in [('requirements','Yêu cầu'),('decisions','Quyết định'),('action_items','Việc cần làm'),('open_questions','Chưa chốt')]:
    lines+=['','### '+title,'']
    for item in report[section]:
        extra=f' Owner: {item["owner"] or "chưa xác nhận"}; due: {item["normalized_due"] or item["raw_due_text"] or "chưa xác nhận"}.' if section=='action_items' else ''
        lines.append('- '+item['text']+extra+' Evidence: '+', '.join(item['evidence_segment_ids'])+'.')
report_text='\n'.join(lines)+'\n'
if expanded and expanded['result']=='PASS':
    report_text=report_text.replace('Meet thật hai participant/DOM, báo cáo dài nhiều map với provider thật, corpus dự án thật và thống kê latency dài hạn vẫn chờ thử.','Meet thật hai participant/DOM, corpus dự án thật và thống kê latency dài hạn vẫn chờ thử. Đã bổ sung báo cáo synthetic 43 turns qua hai map DeepSeek thật trong [EXTENDED_LIVE_REPORT.md](EXTENDED_LIVE_REPORT.md).')
    report_text+='\nBổ sung: [10 kịch bản mới, 6 reports và targeted retest](EXTENDED_LIVE_REPORT.md).\n'
(ROOT/'docs/LIVE_PROVIDER_REPORT.md').write_text(report_text,encoding='utf8')
print(json.dumps(dict(cases=len(cases),reports=2,metrics=metrics)))
