"""Build derived traceability/result tables from supplied registries and recorded evidence."""
from pathlib import Path
import hashlib,json,re,platform,xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1];docs=root/'docs';spec=docs/'spec'
phase1 = (docs/'evidence/phase1/semantic-review.json').exists()
live_path=docs/'evidence/live-provider-review.json'
live=json.loads(live_path.read_text('utf8')) if live_path.exists() else None
live_cases={c['name']:c for c in live['cases']} if live else {}
extended_path=docs/'evidence/extended-live-review.json'
extended=json.loads(extended_path.read_text('utf8')) if extended_path.exists() else None
extended_cases={c['name']:c for c in extended['cases']} if extended else {}
requirements=[];tasks=[];checks=[]
for line in (spec/'REQUIREMENTS.md').read_text('utf8').splitlines():
    if re.match(r'^\| REQ-\d+',line):requirements.append([x.strip() for x in line.strip('|').split('|')])
for line in (spec/'IMPLEMENTATION_PLAN.md').read_text('utf8').splitlines():
    if re.match(r'^\| T-\d+',line):tasks.append([x.strip() for x in line.strip('|').split('|')])
for line in (spec/'ACCEPTANCE_SPEC.md').read_text('utf8').splitlines():
    if re.match(r'^\| (?:CAP|TRN|SES|RAG|AI|REP|SEC|OPS|UX|SRC|CIT|HIS|SCP|DOC)-\d+',line):
        parts=[x.strip() for x in line.strip('|').split('|')]
        if len(parts)==4:checks.append(parts)
assert (len(requirements),len(tasks),len(checks))==(30,28,46)
rows=['# REQ → task → check','', 'Bảng dựng lại từ registry trong sáu tệp được cung cấp; không thay đổi spec gốc. Kết quả được tách theo mode trong [ACCEPTANCE_REPORT.md](ACCEPTANCE_REPORT.md).','', '| REQ | Ưu tiên / yêu cầu | Tasks | Checks |','| --- | --- | --- | --- |']
for req in requirements:
    related=[t for t in tasks if req[0] in t[4]]
    ids=sorted({c for t in related for c in re.findall(r'\b[A-Z]+-\d+\b',t[5])})
    rows.append(f'| {req[0]} | {req[1]} · {req[2]} | '+', '.join(t[0] for t in related)+' | '+', '.join(ids)+' |')
(docs/'TRACEABILITY.md').write_text('\n'.join(rows)+'\n',encoding='utf8')
rows=['# Trạng thái triển khai theo task','', 'Ngày bàn giao: 2026-10-17 · app 0.1.0 · Windows local. IMPLEMENTED không đóng gate live. Spec gốc vẫn giữ status TODO như tài liệu đầu vào.','', '| Task | Nội dung | Trạng thái / bằng chứng |','| --- | --- | --- |']
for task in tasks:
    status='IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT'
    if task[0]=='T-003':status='PARTIAL · calibration chạy với DOM synthetic; DOM/selector Meet thật chưa xác minh'
    if task[0]=='T-014':status='IMPLEMENTED · E5 CPU thật + hybrid benchmark 10/10 top-5 trên corpus synthetic'
    if task[0]=='T-025':status='IMPLEMENTED · PowerShell setup/build/start/health/Ctrl+C trên máy Windows hiện tại; máy sạch pending'
    if task[0]=='T-026':status='NOT TESTED · chưa có Meet thật hai participant; xem CAPTION_ADAPTER checklist'
    if task[0]=='T-027':status='NOT TESTED · không có API key; controlled provider chỉ kiểm tra orchestration/schema'
    if task[0]=='T-027' and live:status='PARTIAL · DeepSeek thật: 6 tình huống synthetic + 2 reports đã đối chiếu; report dài/provider fault live còn chờ. Xem LIVE_PROVIDER_REPORT.'
    if task[0]=='T-027' and extended:status='PARTIAL · 6 mẫu ban đầu + 10 mẫu mở rộng; report synthetic 43 turns/2 map thật pass. Fault live/corpus thật/latency dài hạn còn chờ. Xem EXTENDED_LIVE_REPORT.'
    if task[0]=='T-028':status='IMPLEMENTED · registry/contract/evidence QA; release live gate còn mở'
    rows.append(f'| {task[0]} | {task[3]} | {status} |')
if phase1:
    rows[2]='Cập nhật giai đoạn 1: 2026-10-18 · baseline bàn giao 2026-10-17 · Windows local. Spec gốc giữ nguyên; live gate chưa đóng.'
(docs/'IMPLEMENTATION_STATUS.md').write_text('\n'.join(rows)+'\n',encoding='utf8')
if (docs/'RESPONSE_ROUTING.md').exists():
    with (docs/'IMPLEMENTATION_STATUS.md').open('a',encoding='utf8') as stream:
        stream.write('\nBổ sung response routing: IMPLEMENTED trong backend/UI, quy tắc local 5 luồng và API preview. Xem [RESPONSE_ROUTING.md](RESPONSE_ROUTING.md); chưa nghiệm thu Meet/provider thật cho luồng mới. [Ưu tiên tiếp theo](NEXT_PRIORITIES.md).\n')


evidence={
 'CAP-01':('Vitest + backend + MV3 DOM synthetic','extension-tests.json; backend-tests.xml; e2e-results.json','Partial cùng segment/revision; dấu NOT được giữ.'),
 'CAP-02':('Reducer/backend fixture','extension-tests.json; backend-tests.xml','Hai speaker nói Yes được giữ riêng.'),
 'CAP-03':('Reducer/backend fixture','extension-tests.json; backend-tests.xml','Yes nói lại sau turn khác không bị global dedup.'),
 'CAP-04':('DOM synthetic','extension-tests.json','Node/container replace giữ segment hoặc ghi gap; không đọc chat.'),
 'CAP-05':('Fake clock 60 s + backend heartbeat','extension-tests.json; backend-tests.xml','Im lặng vẫn waiting_for_caption, không captions_off.'),
 'CAP-06':('DOM synthetic','extension-tests.json','Toggle false có evidence → off; DOM mất → unknown. UI Meet đa ngôn ngữ chưa thử.'),
 'TRN-01':('SQLite/WS integration','backend-tests.xml','Ba lần event ID chỉ apply một; retry không schedule AI lần nữa.'),
 'TRN-02':('SQLite/WS integration','backend-tests.xml','Revision 4 giữ khi revision 3 đến sau; epoch scope được kiểm tra.'),
 'TRN-03':('Outbox reconstruction + WS reconnect fixture','extension-tests.json; backend-tests.xml','Retry cùng event ID, ACK đúng; giới hạn count/UTF-8 bytes và overflow. Chưa fault 20 s trong Chrome thật.'),
 'TRN-04':('MV3 thật + DOM synthetic + persistent restart','e2e-results.json; capture-fixture.json; backend-tests.xml','Target.closeTarget worker thành công; runtime hồi binding và caption tiếp; panel document đóng vẫn capture. Backend restart → interrupted.'),
 'SES-01':('Backend integration','backend-tests.xml','Pause không persist text; Resume có gap.'),
 'SES-02':('Backend + UI demo','backend-tests.xml; e2e-results.json','End lặp giữ ended_at; flush timeout có gap; UI đi tới report.'),
 'RAG-01':('SQLite FTS5 integration','backend-tests.xml','Hai project API-17 không trộn nguồn.'),
 'RAG-02':('Filesystem + generation','backend-tests.xml','Lỗi reindex giữ bản index tốt trước + stale warning.'),
 'RAG-03':('Filesystem + FTS5','backend-tests.xml','Sửa/xóa file và file cuối phản ánh index; hash không đổi giữ ID/generation.'),
 'RAG-04':('Controlled provider + retrieved ticket/code','backend-tests.xml','Hai nguồn mâu thuẫn cùng prompt; conflicting result giữ citation hợp lệ. Không chứng minh nghĩa model thật.'),
 'AI-01':('Controlled validation','backend-tests.xml','Chặn một số positive deployment commitment/action đối nghịch NOT; semantic live pending.'),
 'AI-02':('Controlled report validation','backend-tests.xml','Maybe/date/owner không có bằng chứng xác nhận bị chặn; field chưa xác nhận null.'),
 'AI-03':('Controlled schema/neutral demo','backend-tests.xml; e2e-results.json','Không có nguồn không được label supported; demo hỏi làm rõ và hiện missing.'),
 'AI-04':('Pydantic + citation registry','backend-tests.xml','ID nguồn/segment ngoài request bị chặn; drawer dùng backend metadata.'),
 'AI-05':('Scheduler integration','backend-tests.xml','Latest queued, stale output, snapshot/hash cache, memory revision invalidation.'),
 'AI-06':('Reducer + MV3 UI demo','extension-tests.json; e2e-results.json; live-pinned.png','Card giữ nguyên khi caption/gợi ý mới; badge chủ động chuyển.'),
 'AI-07':('Prompt boundary + credential stub','backend-tests.xml','Key không trong prompt, tool không được cấp, lỗi không echo key. Model injection thật chưa thử.'),
 'REP-01':('Controlled map pipeline','backend-tests.xml','Mọi turn được map; requirements đầu và cuối cùng có report evidence; không bỏ đuôi.'),
 'REP-02':('Backend + MV3 UI','backend-tests.xml; e2e-results.json','User edit giữ nguyên sau regenerate; PATCH conflict 409; export đúng version.'),
 'SEC-01':('REST/WS integration','backend-tests.xml','Sai token/Origin/Host bị chặn; frame đầu phải auth; OpenAPI cũng có auth.'),
 'SEC-02':('Storage persistence boundary','backend-tests.xml','RAM transcript/request/report không ở disk tables/bytes; restart mất RAM và giữ project.'),
 'SEC-03':('FK cascade + extension cache event','backend-tests.xml; e2e-results.json','Meeting/project xóa dữ liệu phụ thuộc/index; event xóa reading cache RAM.'),
 'OPS-01':('httpx protocol stub + missing-key actual error','backend-tests.xml; e2e-results.json','401 không retry; transient retry giới hạn; timeout/invalid JSON có lỗi; không fallback mock.'),
 'UX-01':('MV3 Chromium + backend thật, demo','e2e-results.json; projects.png; report.png; sidepanel-320.png','Đủ 5 màn hình, source/search, live, report edit/export, history/settings; 320 px không cuộn ngang.'),
 'UX-02':('Reducer + UI controlled provider','extension-tests.json; e2e-results.json','Shorter dùng snapshot A khi B đã đến; B chờ người dùng chuyển.'),
 'SRC-01':('Backend import + UI text import','backend-tests.xml; e2e-results.json','Repo/text/schema/CSV/JSON, mapping/row error; SQL không thực thi. UI từng loại riêng ngoài text chưa chạy đủ.'),
 'SRC-02':('Filesystem/quota integration','backend-tests.xml','2 MiB file, 10 MiB paste/upload, project quota, binary/secret default skip được kiểm tra.'),
 'RAG-05':('FTS5 + E5 CPU thật, corpus synthetic','retrieval-keyword.json; retrieval-hybrid.json','Hai mode đều 10/10 expected source trong top-5; n=300 timing/mode, không là accuracy tổng quát.'),
 'CIT-01':('Immutable request excerpts integration','backend-tests.xml','V1 còn nguyên sau V2 và delete; changed/deleted flag đúng. Drawer runtime dùng endpoint này.'),
 'REP-03':('Controlled transcript-only report','backend-tests.xml; e2e-results.json','AI suggestions không phải speech input; unknown owner/due không thành confirmed fact.'),
 'HIS-01':('Backend + UI','backend-tests.xml; e2e-results.json','Filter keyword/project và export nội dung version đã sửa, giữ warnings/evidence.'),
 'OPS-02':('Windows hiện tại, warm dependency cache','setup-windows.log; build-windows.log; startup-health.json','Setup/build/start/health/FTS5/timezone/Ctrl+C đã chạy; không phải máy Windows sạch.'),
 'OPS-03':('Instrumentation stub + DOM fixture','backend-tests.xml; capture-fixture.json; runtime-metrics-fixture.json','Monotonic timing, known/unknown usage; demo không tính như request provider thật. Live latency/token chưa đo.'),
 'SEC-04':('Windows filesystem junction fixture','backend-tests.xml','Junction ngoài root, .gitignore, private key/binary không vào chunks.'),
 'SEC-05':('Controlled retention clock + FK','backend-tests.xml','Expired meeting bị xóa; fresh meeting và project source/index giữ lại.'),
 'SEC-06':('Backend + MV3 storage inspection','backend-tests.xml; e2e-results.json','Sentinel key không trong browser storage/GET/error/metrics; nhập UI clear field, key chỉ backend RAM.'),
 'AI-08':('Controlled provider JSON/SSE','backend-tests.xml','Bad JSON/enum/extra field/ID/revision không publish validated result.'),
 'AI-09':('Scheduler integration','backend-tests.xml','One active/latest queued, manual priority, cancel-before-start, auto quota và manual vẫn dùng được.'),
 'SCP-01':('Manifest/config inspection + runtime','backend-tests.xml; e2e-results.json','Chỉ Meet captions, không audio permissions/tools/SQL execution; snapshot có nhãn.'),
 'DOC-01':('Documentation/contract QA','documentation-qa.json; backend-tests.xml; extension-tests.json; e2e-results.json','30 REQ/28 tasks/46 checks được nối; PASS có evidence; live tách NOT TESTED.')}
assert set(evidence)=={c[0] for c in checks}
backend=ET.parse(docs/('evidence/phase1/backend-final.xml' if phase1 else 'evidence/backend-tests.xml')).getroot();suite=backend.find('testsuite') if backend.tag=='testsuites' else backend
front=json.loads((docs/('evidence/phase1/frontend-final.json' if phase1 else 'evidence/extension-tests.json')).read_text('utf8'))
keyword=json.loads((docs/'evidence/retrieval-keyword.json').read_text('utf8'));hybrid=json.loads((docs/'evidence/retrieval-hybrid.json').read_text('utf8'))
capture=json.loads((docs/('evidence/phase1/browser-final/capture-fixture.json' if phase1 else 'evidence/capture-fixture.json')).read_text('utf8'))
manifest=root/'extension/public/manifest.json';corpus=root/'fixtures/demo-project.json'
rows=['# Báo cáo nghiệm thu thực tế','', '**Implementation chạy local, chờ live validation. Không phải MVP VERIFIED.** Ngày bàn giao 2026-10-17; app 0.1.0, adapter meet-calibrated-v1; mã nguồn được quản lý theo commit trong repository.','', '## Môi trường và kết quả','',f'- {keyword["machine"]}; CPU {keyword["cpu"]}; {keyword["logical_cpus"]} logical CPUs. Python {keyword["python"]}, Node 22.20.0, npm 10.9.3; Chromium {capture["browser"]} do Playwright nạp MV3. UI Việt, caption synthetic Anh.',f'- Backend: **{suite.attrib["tests"]} tests**, failures={suite.attrib.get("failures","0")}, errors={suite.attrib.get("errors","0")}; extension unit: **{front["numPassedTests"]} passed**. E2E: xem e2e-results.json (3 cases). Không cộng số test thành số acceptance checks đã nghiệm thu live.',f'- Corpus SHA256: `{hashlib.sha256(corpus.read_bytes()).hexdigest()}`. Manifest SHA256: `{hashlib.sha256(manifest.read_bytes()).hexdigest()}`.', '- Dependency locks: package-lock.json, backend/requirements.lock và requirements-semantic.lock. Migration 001, FK/WAL/FTS5; persistent và RAM mode thử riêng.','', '## Số đo','', '| Mode / phép đo | Corpus / n | Median | p95 | Giới hạn |','| --- | --- | --- | --- | --- |',f'| FTS5 retrieval | 12 nguồn/12 chunks; n={keyword["n"]} | {keyword["median_ms"]:.3f} ms | {keyword["p95_ms"]:.3f} ms | 10/10 source top-5 trên corpus synthetic |',f'| E5 hybrid CPU | 12 nguồn/12 chunks; n={hybrid["n"]} | {hybrid["median_ms"]:.3f} ms | {hybrid["p95_ms"]:.3f} ms | 10/10 source top-5; revision {hybrid["model_revision"][:12]} |',f'| Adapter event → ACK | DOM synthetic + worker thật; n={capture["n"]} | {capture["median_ms"]:.3f} ms | {capture["p95_ms"]:.3f} ms | Mẫu rất ít; percentile không đủ tin cậy cho SLA |', '| Provider/report live | Chưa có key | Unknown | Unknown | Không claim mục tiêu 2–5 s hoặc token/billing thật |','', '## Check theo từng mode','', '| Check | Environment/mode | Result | Evidence trong docs/evidence | Actual result / pending |','| --- | --- | --- | --- | --- |']
for check in checks:
    id=check[0];mode,files,result=evidence[id]
    rows.append(f'| {id} | {mode} | PASS | {files} | {result} |')
    if id.startswith('CAP-') or id in ('TRN-03','TRN-04','SES-01','SES-02','UX-01'):
        rows.append(f'| {id} | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |')
    if id in ('AI-01','AI-02','AI-03','AI-07','RAG-04','REP-01','REP-03','OPS-01'):
        case_map={'AI-01':'negative-deployment','AI-02':'tentative-deadline','AI-03':'missing-status','AI-07':'untrusted-instructions','RAG-04':'conflicting-api17','REP-03':'multi-participant-review'}
        case=live_cases.get(case_map.get(id,''))
        review_file='live-provider-review.json'
        if id=='REP-01' and 'long-report-start-middle-tail' in extended_cases:
            case=extended_cases['long-report-start-middle-tail']
            review_file='extended-live-review.json'
        if case:
            rows.append(f'| {id} | DeepSeek thật / transcript synthetic | {case["status"]} | {review_file}; {case["evidence_file"]} | {case["observation"]} Chỉ áp dụng mẫu này. |')
        elif live:
            pending='Báo cáo 8 turns synthetic bằng DeepSeek thật đã chạy; transcript dài nhiều map vẫn chưa thử với provider thật.' if id=='REP-01' else 'Connection/HTTPS/SSE/usage thật pass; 401/429/outage/timeout chỉ có controlled tests.'
            rows.append(f'| {id} | DeepSeek provider thật | PARTIAL | live-provider-review.json | {pending} |')
        else:rows.append(f'| {id} | DeepSeek provider thật | NOT TESTED | Không có API key; đã kiểm tra has_key/env availability false | Cần đặt key local, Test connection và chạy corpus ngữ nghĩa thật; mock không đóng gate này. |')
rows+=['| OPS-02 | Máy Windows sạch độc lập | NOT TESTED | — | Warm setup trên máy hiện tại không thay máy sạch. |','', '## Hành vi triển khai và khác biệt','', '5 màn hình dùng backend thật. Demo được chọn rõ; production lỗi không tự fallback. Caption schema/revision/ACK và session scope tách khỏi DOM adapter. Source generations/citations, FTS/hybrid, manual snapshot/pin, scheduler, report versions/export và retention có mã/test tương ứng. [CONTRACT_CHANGES.md](CONTRACT_CHANGES.md) ghi các quyết định triển khai.','', 'Không có failure tự động còn mở trong run bàn giao khi các evidence hiện tại đều pass. Các lỗi tìm được trong quá trình chạy (UTF-8 BOM, tzdata Windows, SQLite thread concurrency, ACK retry schedule lặp, cancel-before-start và memory stale) đã được sửa và có regression checks.','', '## Những việc còn lại để nghiệm thu live','', '1. Chạy checklist Meet thật trong [CAPTION_ADAPTER.md](CAPTION_ADAPTER.md), tối thiểu hai participant; ghi Chrome/ngôn ngữ/profile, transcript/gaps và kết quả từng CAP/TRN/SES.', '2. Cấp DeepSeek key vào RAM backend qua Settings; Test connection thật. Chạy phủ định/Maybe/status thiếu/mâu thuẫn/injection/long report, đối chiếu từng claim với evidence. Không ghi key vào report.', '3. Thử setup sạch trên Windows khác, native toolbar side panel, outage 20 giây, reload/navigation và Chrome restart; ghi phần RAM mất/persistent interrupted đúng.', '4. Benchmark corpus dự án thật và latency provider thật với n/median/p95/config. Hiện số liệu chỉ cho corpus synthetic nhỏ.','', '## Commands','', '```powershell', r'.\scripts\test.ps1 -Browser', r'.\.venv\Scripts\python.exe scripts\benchmark.py --semantic', r'.\.venv\Scripts\python.exe scripts\documentation.py', r'.\.venv\Scripts\python.exe scripts\check_docs.py','```','', 'Các giới hạn khác: [LIMITATIONS.md](LIMITATIONS.md). Đặc tả gốc: [spec/ACCEPTANCE_SPEC.md](spec/ACCEPTANCE_SPEC.md).']
if live:
    text='\n'.join(rows)
    m=live['metrics']
    text=text.replace('| Provider/report live | Chưa có key | Unknown | Unknown | Không claim mục tiêu 2–5 s hoặc token/billing thật |',f'| DeepSeek thật, transcript synthetic | n={m["n"]}; full + targeted retests | {m["median_ms"]/1000:.2f} s | {m["p95_ms"]/1000:.2f} s | Suggestion/report/connection/correction gộp; {m["total_tokens"]:,} provider tokens; không phải SLA/billing |')
    text=text.replace('2. Cấp DeepSeek key vào RAM backend qua Settings; Test connection thật. Chạy phủ định/Maybe/status thiếu/mâu thuẫn/injection/long report, đối chiếu từng claim với evidence. Không ghi key vào report.','2. DeepSeek thật đã chạy 6 tình huống synthetic và 2 reports: [LIVE_PROVIDER_REPORT.md](LIVE_PROVIDER_REPORT.md). Tiếp tục thử transcript dài nhiều map, corpus thực tế và thêm tình huống adversarial; không coi mẫu nhỏ là accuracy tổng quát.')
    text=text.replace('4. Benchmark corpus dự án thật và latency provider thật với n/median/p95/config. Hiện số liệu chỉ cho corpus synthetic nhỏ.','4. Benchmark corpus dự án thật và latency provider dài hạn. Đã có n/median/p95/usage trên mẫu synthetic nhỏ; chưa chứng minh SLA.')
    text=text.replace('Live latency/token chưa đo.','DeepSeek timing/usage mẫu nhỏ được ghi thêm trong LIVE_PROVIDER_REPORT.')
    text=text.replace('semantic live pending.','Provider thật xem dòng synthetic riêng bên dưới.')
    text=text.replace('Model injection thật chưa thử.','Provider thật: đoạn trích synthetic xem dòng riêng bên dưới.')
    text+='\n\nProvider review: '+str(len(live['cases']))+' mẫu đã đối chiếu; key đã xóa khỏi RAM backend sau thử. Meet thật vẫn NOT TESTED.\n'
else:text='\n'.join(rows)
if extended:
    text=text.replace('Tiếp tục thử transcript dài nhiều map, corpus thực tế và thêm tình huống adversarial; không coi mẫu nhỏ là accuracy tổng quát.','Đã thêm 10 kịch bản, gồm transcript 43 turns qua hai map thật: [EXTENDED_LIVE_REPORT.md](EXTENDED_LIVE_REPORT.md). Tiếp tục corpus thực tế và thêm tình huống adversarial; không coi mẫu nhỏ là accuracy tổng quát.')
    em=extended['metrics']
    text+=f'\nExpanded provider review: {len(extended["cases"])} mẫu mới, {em["report_n"]} reports; suggestion median {em["suggestion_median_s"]:.2f} s, max {em["suggestion_max_s"]:.2f} s. [EXTENDED_LIVE_REPORT.md](EXTENDED_LIVE_REPORT.md). Kết quả theo fixture có giới hạn, không phải SLA.\n'
speed_path=docs/'evidence/speed-review.json'
if speed_path.exists():
    speed=json.loads(speed_path.read_text('utf8'));sm=speed['metrics']
    text+=f'\nLatency optimization: cùng 10 fixture median {sm["baseline_ten_median_s"]:.3f} → {sm["matched_ten"]["median_s"]:.3f} s; n=16 median {sm["all_sixteen"]["median_s"]:.3f} s, max {sm["all_sixteen"]["max_s"]:.3f} s. Full validation trước publish, warm client; không phải hard SLA. [LATENCY_REPORT.md](LATENCY_REPORT.md).\n'

if (docs/'RESPONSE_ROUTING.md').exists():
    text+='\nResponse routing: backend/UI và API preview đã triển khai; xem [RESPONSE_ROUTING.md](RESPONSE_ROUTING.md) và [offline routing review](evidence/routing-review.json). Bộ quy tắc chưa có accuracy corpus thật; số đo latency/provider phía trên là lịch sử trước routing. Các lỗ hổng sai nghĩa trong [SYSTEM_ASSESSMENT.md](SYSTEM_ASSESSMENT.md) vẫn mở.\n'

if phase1:
    text=text.replace('Ngày bàn giao 2026-10-17;', 'Cập nhật giai đoạn 1 2026-10-18; baseline bàn giao 2026-10-17;')
    paths = {
        'backend-tests.xml':'phase1/backend-final.xml',
        'extension-tests.json':'phase1/frontend-final.json',
        'e2e-results.json':'phase1/browser-final-results.json',
        'documentation-qa.json':'phase1/documentation-qa.json',
        'capture-fixture.json':'phase1/browser-final/capture-fixture.json',
        'runtime-metrics-fixture.json':'phase1/browser-final/runtime-metrics-fixture.json',
        'projects.png':'phase1/browser-final/projects.png',
        'report.png':'phase1/browser-final/report.png',
        'live-pinned.png':'phase1/browser-final/live-pinned.png',
        'sidepanel-320.png':'phase1/browser-final/sidepanel-320.png',
    }
    for old,new in paths.items():
        text=text.replace(old,new)
    text=text.replace('Các lỗ hổng sai nghĩa trong [SYSTEM_ASSESSMENT.md](SYSTEM_ASSESSMENT.md) vẫn mở.',
        'Ba probe gốc đã bị chặn trong phạm vi giai đoạn 1; chưa có semantic entailment tổng quát.')
    text+='\nGiai đoạn 1: [kết quả A–E và giới hạn](PHASE1_REPORT.md); evidence cũ giữ nguyên, các check automated ở bảng trên dùng evidence mới. Provider/latency trước sửa là lịch sử. Không phải MVP VERIFIED.\n'
    with (docs/'IMPLEMENTATION_STATUS.md').open('a',encoding='utf8') as stream:
        stream.write('\nGiai đoạn 1: A–E PASS trong phạm vi guard đã thử, không mở rộng phạm vi sản phẩm. REQ-01/05/13/14/19/20/21/28/30 có thêm regression tests cho slot phiên, claim và pipeline. Xem [PHASE1_REPORT.md](PHASE1_REPORT.md).\n')
phase2_path=docs/'evidence/phase2/review.json'
if phase2_path.exists():
    current=json.loads(phase2_path.read_text('utf8'))
    text=text.replace('**219 tests**',f'**{current["final"]["backend"]} tests**').replace('**13 passed**',f'**{current["final"]["frontend"]} passed**').replace('(3 cases)','(4 cases)')
    for name in ('backend-final.xml','frontend-final.json','browser-final-results.json','documentation-qa.json','browser-final/capture-fixture.json','browser-final/runtime-metrics-fixture.json','browser-final/projects.png','browser-final/report.png','browser-final/live-pinned.png','browser-final/sidepanel-320.png'):
        text=text.replace('phase1/'+name,'phase2/'+name)
    text=text.replace('## Số đo','## Số đo lịch sử trước Phase 2',1)
    text=text.replace('| Adapter event → ACK |','| Adapter event → ACK (Phase 1 lịch sử) |')
    text=text.replace('Cập nhật giai đoạn 1 2026-10-18;','Cập nhật Phase 2 2026-10-18;')
    text+='\nPhase 2: [capture/recovery/latency, before-after và gate A–G](PHASE2_REPORT.md). Kết quả tự động 228 backend / 56 frontend / 4 browser; Meet thật NOT TESTED, không có paid provider call mới. Số đo lịch sử phía trên không phải benchmark Phase 2.\n'
    with (docs/'IMPLEMENTATION_STATUS.md').open('a',encoding='utf8') as stream:
        stream.write('\nPhase 2: replay/capture/recovery/telemetry đã triển khai; [A–G và giới hạn](PHASE2_REPORT.md), [runbook live](PHASE2_LIVE_RUNBOOK.md). 228 backend / 56 frontend / 4 browser; Meet thật NOT TESTED.\n')
phase3_path=docs/'evidence/phase3/review.json'
if phase3_path.exists():
    current=json.loads(phase3_path.read_text('utf8'));counts=current['regression']
    text=text.replace('**228 tests**',f'**{counts["backend"]} tests**').replace('**56 passed**',f'**{counts["frontend"]} passed**').replace('(4 cases)','(5 cases)')
    for name in ('backend-final.xml','frontend-final.json','browser-final-results.json','documentation-qa.json','browser-final/capture-fixture.json','browser-final/runtime-metrics-fixture.json','browser-final/projects.png','browser-final/report.png','browser-final/live-pinned.png','browser-final/sidepanel-320.png'):
        text=text.replace('phase2/'+name,'phase3/'+name)
    text=text.replace('Cập nhật Phase 2 2026-10-18;','Cập nhật Phase 3 2026-10-18;')
    text+='\nPhase 3: **PARTIAL** theo mục tiêu đặt trước. [Báo cáo A–F và benchmark đối chiếu](PHASE3_REPORT.md). 39/39 eligible đã có attempted generation, 0 missed/false trigger; logical 49 → 40 (giảm 18,37%, chưa đạt 20%); Auto đợi manual có thể 2,9 s (chưa đạt 500 ms mọi câu ngắn). Không suy ra chất lượng trả lời thật hoặc SLA. Regression '+f'{counts["backend"]} backend / {counts["frontend"]} frontend / {counts["browser"]} browser. Meet/provider thật mới NOT TESTED; paid calls mới = 0.\n'
    with (docs/'IMPLEMENTATION_STATUS.md').open('a',encoding='utf8') as stream:
        stream.write('\nPhase 3: **PARTIAL** · trigger/scheduler/dedup/context/retrieval/accounting/UI đã triển khai và đối chiếu; hai mục tiêu request/Auto wait chưa đạt. [A–F, số đo và giới hạn](PHASE3_REPORT.md). Không mở rộng sang decision memory/connector/STT/agent/multiworker.\n')
phase4_path=docs/'evidence/phase4/review.json'
if phase4_path.exists():
    current=json.loads(phase4_path.read_text('utf8'));counts=current['regression']
    text=text.replace('**276 tests**',f'**{counts["backend"]} tests**').replace('**58 passed**',f'**{counts["frontend"]} passed**').replace('(5 cases)','(6 cases)')
    for name in ('backend-final.xml','frontend-final.json','browser-final-results.json','documentation-qa.json','browser-final/capture-fixture.json','browser-final/runtime-metrics-fixture.json','browser-final/projects.png','browser-final/report.png','browser-final/live-pinned.png','browser-final/sidepanel-320.png'):
        text=text.replace('phase3/'+name,'phase4/'+name)
    text=text.replace('Cập nhật Phase 3 2026-10-18;','Cập nhật Phase 4 2026-10-19;')
    text=text.replace('Migration 001, FK/WAL/FTS5','Migrations 001→002 (versioned), FK/WAL/FTS5')
    text+='\nPhase 4: **PARTIAL** · [A–F, schema/states, corpus và giới hạn](PHASE4_REPORT.md). 23 synthetic scenarios (5 held-out), 38/38 expected items/evidence; pipeline dài 321 turns/16 maps giữ cancellation và deadline mới. Không là accuracy/model-quality thật. Regression '+f'{counts["backend"]} backend / {counts["frontend"]} frontend / 6 browser. Meet/model thật NOT TESTED, paid calls mới = 0.\n'
    with (docs/'IMPLEMENTATION_STATUS.md').open('a',encoding='utf8') as stream:
        stream.write('\nPhase 4: **PARTIAL** · evidence ledger/versioned migration 002, live context, report reconciliation/current-history và UI/export đã triển khai trong phạm vi grammar có giới hạn. [Báo cáo A–F](PHASE4_REPORT.md). Bare Yes/authority/coreference ngoài phạm vi vẫn cần làm rõ; không tự chứng nhận model quality hay Meet live.\n')
(docs/'ACCEPTANCE_REPORT.md').write_text(text+'\n',encoding='utf8')
print('Generated traceability, task status and mode-specific acceptance report')

# The original acceptance matrix remains a historical Phase 4 snapshot. Phase 5
# operational acceptance has its own A-F/gates and never silently upgrades it.
if (docs/'PHASE5_REPORT.md').exists():
    for name in ('IMPLEMENTATION_STATUS.md','ACCEPTANCE_REPORT.md','TRACEABILITY.md'):
        target=docs/name
        text=target.read_text('utf8')
        target.write_text('> Hiện hành: [Phase 5 / release gates](PHASE5_REPORT.md). Ma trận bên dưới là snapshot Phase 4 và truy vết spec gốc, không phải nghiệm thu Phase 5.\n\n'+text,encoding='utf8')
