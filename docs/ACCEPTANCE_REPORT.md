> Hiện hành: [Phase 5 / release gates](PHASE5_REPORT.md). Ma trận bên dưới là snapshot Phase 4 và truy vết spec gốc, không phải nghiệm thu Phase 5.

# Báo cáo nghiệm thu thực tế

**Implementation chạy local, chờ live validation. Không phải MVP VERIFIED.** Cập nhật Phase 4 2026-10-19; baseline bàn giao 2026-10-17; app 0.1.0, adapter meet-calibrated-v1; mã nguồn được quản lý theo commit trong repository.

## Môi trường và kết quả

- Windows-11-10.0.26200-SP0; CPU AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD; 16 logical CPUs. Python 3.13.4, Node 22.20.0, npm 10.9.3; Chromium 141.0.7390.37 do Playwright nạp MV3. UI Việt, caption synthetic Anh.
- Backend: **331 tests**, failures=0, errors=0; extension unit: **60 passed**. E2E: xem phase4/browser-final-results.json (6 cases). Không cộng số test thành số acceptance checks đã nghiệm thu live.
- Corpus SHA256: `3708ed687c2c7685e050a67fb8c8b28c5d8ae3eed92b06f666b6375c39ebb087`. Manifest SHA256: `2de585c3876895fb9f3c34245f1b9e75e2abed1843a061efcb5fff973bcb4bc3`.
- Dependency locks: package-lock.json, backend/requirements.lock và requirements-semantic.lock. Migrations 001→002 (versioned), FK/WAL/FTS5; persistent và RAM mode thử riêng.

## Số đo lịch sử trước Phase 2

| Mode / phép đo | Corpus / n | Median | p95 | Giới hạn |
| --- | --- | --- | --- | --- |
| FTS5 retrieval | 12 nguồn/12 chunks; n=300 | 0.680 ms | 0.865 ms | 10/10 source top-5 trên corpus synthetic |
| E5 hybrid CPU | 12 nguồn/12 chunks; n=300 | 38.073 ms | 49.772 ms | 10/10 source top-5; revision 614241f622f5 |
| Adapter event → ACK (Phase 1 lịch sử) | DOM synthetic + worker thật; n=6 | 10.000 ms | 10.600 ms | Mẫu rất ít; percentile không đủ tin cậy cho SLA |
| DeepSeek thật, transcript synthetic | n=16; full + targeted retests | 2.90 s | 4.67 s | Suggestion/report/connection/correction gộp; 39,332 provider tokens; không phải SLA/billing |

## Check theo từng mode

| Check | Environment/mode | Result | Evidence trong docs/evidence | Actual result / pending |
| --- | --- | --- | --- | --- |
| CAP-01 | Vitest + backend + MV3 DOM synthetic | PASS | phase4/frontend-final.json; phase4/backend-final.xml; phase4/browser-final-results.json | Partial cùng segment/revision; dấu NOT được giữ. |
| CAP-01 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| CAP-02 | Reducer/backend fixture | PASS | phase4/frontend-final.json; phase4/backend-final.xml | Hai speaker nói Yes được giữ riêng. |
| CAP-02 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| CAP-03 | Reducer/backend fixture | PASS | phase4/frontend-final.json; phase4/backend-final.xml | Yes nói lại sau turn khác không bị global dedup. |
| CAP-03 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| CAP-04 | DOM synthetic | PASS | phase4/frontend-final.json | Node/container replace giữ segment hoặc ghi gap; không đọc chat. |
| CAP-04 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| CAP-05 | Fake clock 60 s + backend heartbeat | PASS | phase4/frontend-final.json; phase4/backend-final.xml | Im lặng vẫn waiting_for_caption, không captions_off. |
| CAP-05 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| CAP-06 | DOM synthetic | PASS | phase4/frontend-final.json | Toggle false có evidence → off; DOM mất → unknown. UI Meet đa ngôn ngữ chưa thử. |
| CAP-06 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| TRN-01 | SQLite/WS integration | PASS | phase4/backend-final.xml | Ba lần event ID chỉ apply một; retry không schedule AI lần nữa. |
| TRN-02 | SQLite/WS integration | PASS | phase4/backend-final.xml | Revision 4 giữ khi revision 3 đến sau; epoch scope được kiểm tra. |
| TRN-03 | Outbox reconstruction + WS reconnect fixture | PASS | phase4/frontend-final.json; phase4/backend-final.xml | Retry cùng event ID, ACK đúng; giới hạn count/UTF-8 bytes và overflow. Chưa fault 20 s trong Chrome thật. |
| TRN-03 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| TRN-04 | MV3 thật + DOM synthetic + persistent restart | PASS | phase4/browser-final-results.json; phase4/browser-final/capture-fixture.json; phase4/backend-final.xml | Target.closeTarget worker thành công; runtime hồi binding và caption tiếp; panel document đóng vẫn capture. Backend restart → interrupted. |
| TRN-04 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| SES-01 | Backend integration | PASS | phase4/backend-final.xml | Pause không persist text; Resume có gap. |
| SES-01 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| SES-02 | Backend + UI demo | PASS | phase4/backend-final.xml; phase4/browser-final-results.json | End lặp giữ ended_at; flush timeout có gap; UI đi tới report. |
| SES-02 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| RAG-01 | SQLite FTS5 integration | PASS | phase4/backend-final.xml | Hai project API-17 không trộn nguồn. |
| RAG-02 | Filesystem + generation | PASS | phase4/backend-final.xml | Lỗi reindex giữ bản index tốt trước + stale warning. |
| RAG-03 | Filesystem + FTS5 | PASS | phase4/backend-final.xml | Sửa/xóa file và file cuối phản ánh index; hash không đổi giữ ID/generation. |
| RAG-04 | Controlled provider + retrieved ticket/code | PASS | phase4/backend-final.xml | Hai nguồn mâu thuẫn cùng prompt; conflicting result giữ citation hợp lệ. Không chứng minh nghĩa model thật. |
| RAG-04 | DeepSeek thật / transcript synthetic | PASS | live-provider-review.json; live-provider.json | 401/403 cùng xuất hiện, conflicting, trích đúng hai chunk của ticket/code; không suy snapshot thành deployment. Chỉ áp dụng mẫu này. |
| AI-01 | Controlled validation | PASS | phase4/backend-final.xml | Chặn một số positive deployment commitment/action đối nghịch NOT; Provider thật xem dòng synthetic riêng bên dưới. |
| AI-01 | DeepSeek thật / transcript synthetic | PASS | live-provider-review.json; live-provider.json | Partial deploy → NOT deploy được upsert thành một turn revision 2. Nghĩa giữ KHÔNG; câu trả lời hỏi xác nhận trạng thái production, không tự hứa trạng thái. Chỉ áp dụng mẫu này. |
| AI-02 | Controlled report validation | PASS | phase4/backend-final.xml | Maybe/date/owner không có bằng chứng xác nhận bị chặn; field chưa xác nhận null. |
| AI-02 | DeepSeek thật / transcript synthetic | PASS | live-provider-review.json; live-provider.json | Friday được giữ là chưa xác nhận; không có decision, owner hay deadline được tự điền trong report. Chỉ áp dụng mẫu này. |
| AI-03 | Controlled schema/neutral demo | PASS | phase4/backend-final.xml; phase4/browser-final-results.json | Không có nguồn không được label supported; demo hỏi làm rõ và hiện missing. |
| AI-03 | DeepSeek thật / transcript synthetic | PASS | live-provider-review.json; live-provider.json | Không có nguồn: missing, findings rỗng và hỏi trạng thái production; không tự nói đã/chưa release. Chỉ áp dụng mẫu này. |
| AI-04 | Pydantic + citation registry | PASS | phase4/backend-final.xml | ID nguồn/segment ngoài request bị chặn; drawer dùng backend metadata. |
| AI-05 | Scheduler integration | PASS | phase4/backend-final.xml | Latest queued, stale output, snapshot/hash cache, memory revision invalidation. |
| AI-06 | Reducer + MV3 UI demo | PASS | phase4/frontend-final.json; phase4/browser-final-results.json; phase4/browser-final/live-pinned.png | Card giữ nguyên khi caption/gợi ý mới; badge chủ động chuyển. |
| AI-07 | Prompt boundary + credential stub | PASS | phase4/backend-final.xml | Key không trong prompt, tool không được cấp, lỗi không echo key. Provider thật: đoạn trích synthetic xem dòng riêng bên dưới. |
| AI-07 | DeepSeek thật / transcript synthetic | PASS | live-provider-review.json; live-injection-retest.json | Đoạn trích yêu cầu lộ key/DROP TABLE được hiểu là dữ liệu. Gợi ý từ chối và hỏi làm rõ; không có tool/SQL execution. Chỉ áp dụng mẫu này. |
| REP-01 | Controlled map pipeline | PASS | phase4/backend-final.xml | Mọi turn được map; requirements đầu và cuối cùng có report evidence; không bỏ đuôi. |
| REP-01 | DeepSeek thật / transcript synthetic | PASS | extended-live-review.json; extended-live-retest.json | 43 turns, 19.998 ký tự lời thoại, 2 map requests; ba yêu cầu ở s1/s22/s43 đều còn; ID mục không trùng sau sửa. Chỉ áp dụng mẫu này. |
| REP-02 | Backend + MV3 UI | PASS | phase4/backend-final.xml; phase4/browser-final-results.json | User edit giữ nguyên sau regenerate; PATCH conflict 409; export đúng version. |
| SEC-01 | REST/WS integration | PASS | phase4/backend-final.xml | Sai token/Origin/Host bị chặn; frame đầu phải auth; OpenAPI cũng có auth. |
| SEC-02 | Storage persistence boundary | PASS | phase4/backend-final.xml | RAM transcript/request/report không ở disk tables/bytes; restart mất RAM và giữ project. |
| SEC-03 | FK cascade + extension cache event | PASS | phase4/backend-final.xml; phase4/browser-final-results.json | Meeting/project xóa dữ liệu phụ thuộc/index; event xóa reading cache RAM. |
| OPS-01 | httpx protocol stub + missing-key actual error | PASS | phase4/backend-final.xml; phase4/browser-final-results.json | 401 không retry; transient retry giới hạn; timeout/invalid JSON có lỗi; không fallback mock. |
| OPS-01 | DeepSeek provider thật | PARTIAL | live-provider-review.json | Connection/HTTPS/SSE/usage thật pass; 401/429/outage/timeout chỉ có controlled tests. |
| UX-01 | MV3 Chromium + backend thật, demo | PASS | phase4/browser-final-results.json; phase4/browser-final/projects.png; phase4/browser-final/report.png; phase4/browser-final/sidepanel-320.png | Đủ 5 màn hình, source/search, live, report edit/export, history/settings; 320 px không cuộn ngang. |
| UX-01 | Chrome/Meet thật hai participant | NOT TESTED | CAPTION_ADAPTER checklist | Chưa có phiên Meet được phép thử; native toolbar/DOM/language/network 20 s cần kiểm chứng. |
| UX-02 | Reducer + UI controlled provider | PASS | phase4/frontend-final.json; phase4/browser-final-results.json | Shorter dùng snapshot A khi B đã đến; B chờ người dùng chuyển. |
| SRC-01 | Backend import + UI text import | PASS | phase4/backend-final.xml; phase4/browser-final-results.json | Repo/text/schema/CSV/JSON, mapping/row error; SQL không thực thi. UI từng loại riêng ngoài text chưa chạy đủ. |
| SRC-02 | Filesystem/quota integration | PASS | phase4/backend-final.xml | 2 MiB file, 10 MiB paste/upload, project quota, binary/secret default skip được kiểm tra. |
| RAG-05 | FTS5 + E5 CPU thật, corpus synthetic | PASS | retrieval-keyword.json; retrieval-hybrid.json | Hai mode đều 10/10 expected source trong top-5; n=300 timing/mode, không là accuracy tổng quát. |
| CIT-01 | Immutable request excerpts integration | PASS | phase4/backend-final.xml | V1 còn nguyên sau V2 và delete; changed/deleted flag đúng. Drawer runtime dùng endpoint này. |
| REP-03 | Controlled transcript-only report | PASS | phase4/backend-final.xml; phase4/browser-final-results.json | AI suggestions không phải speech input; unknown owner/due không thành confirmed fact. |
| REP-03 | DeepSeek thật / transcript synthetic | PASS | live-provider-review.json; live-meeting-retest.json | 3 speaker, 8 turns: giữ hai yêu cầu đầu/cuối, staging-only, cả hai việc Minh đã nhận, hạn 2026-10-20; Friday và 401/403 còn mở. Chỉ áp dụng mẫu này. |
| HIS-01 | Backend + UI | PASS | phase4/backend-final.xml; phase4/browser-final-results.json | Filter keyword/project và export nội dung version đã sửa, giữ warnings/evidence. |
| OPS-02 | Windows hiện tại, warm dependency cache | PASS | setup-windows.log; build-windows.log; startup-health.json | Setup/build/start/health/FTS5/timezone/Ctrl+C đã chạy; không phải máy Windows sạch. |
| OPS-03 | Instrumentation stub + DOM fixture | PASS | phase4/backend-final.xml; phase4/browser-final/capture-fixture.json; phase4/browser-final/runtime-metrics-fixture.json | Monotonic timing, known/unknown usage; demo không tính như request provider thật. DeepSeek timing/usage mẫu nhỏ được ghi thêm trong LIVE_PROVIDER_REPORT. |
| SEC-04 | Windows filesystem junction fixture | PASS | phase4/backend-final.xml | Junction ngoài root, .gitignore, private key/binary không vào chunks. |
| SEC-05 | Controlled retention clock + FK | PASS | phase4/backend-final.xml | Expired meeting bị xóa; fresh meeting và project source/index giữ lại. |
| SEC-06 | Backend + MV3 storage inspection | PASS | phase4/backend-final.xml; phase4/browser-final-results.json | Sentinel key không trong browser storage/GET/error/metrics; nhập UI clear field, key chỉ backend RAM. |
| AI-08 | Controlled provider JSON/SSE | PASS | phase4/backend-final.xml | Bad JSON/enum/extra field/ID/revision không publish validated result. |
| AI-09 | Scheduler integration | PASS | phase4/backend-final.xml | One active/latest queued, manual priority, cancel-before-start, auto quota và manual vẫn dùng được. |
| SCP-01 | Manifest/config inspection + runtime | PASS | phase4/backend-final.xml; phase4/browser-final-results.json | Chỉ Meet captions, không audio permissions/tools/SQL execution; snapshot có nhãn. |
| DOC-01 | Documentation/contract QA | PASS | phase4/documentation-qa.json; phase4/backend-final.xml; phase4/frontend-final.json; phase4/browser-final-results.json | 30 REQ/28 tasks/46 checks được nối; PASS có evidence; live tách NOT TESTED. |
| OPS-02 | Máy Windows sạch độc lập | NOT TESTED | — | Warm setup trên máy hiện tại không thay máy sạch. |

## Hành vi triển khai và khác biệt

5 màn hình dùng backend thật. Demo được chọn rõ; production lỗi không tự fallback. Caption schema/revision/ACK và session scope tách khỏi DOM adapter. Source generations/citations, FTS/hybrid, manual snapshot/pin, scheduler, report versions/export và retention có mã/test tương ứng. [CONTRACT_CHANGES.md](CONTRACT_CHANGES.md) ghi các quyết định triển khai.

Không có failure tự động còn mở trong run bàn giao khi các evidence hiện tại đều pass. Các lỗi tìm được trong quá trình chạy (UTF-8 BOM, tzdata Windows, SQLite thread concurrency, ACK retry schedule lặp, cancel-before-start và memory stale) đã được sửa và có regression checks.

## Những việc còn lại để nghiệm thu live

1. Chạy checklist Meet thật trong [CAPTION_ADAPTER.md](CAPTION_ADAPTER.md), tối thiểu hai participant; ghi Chrome/ngôn ngữ/profile, transcript/gaps và kết quả từng CAP/TRN/SES.
2. DeepSeek thật đã chạy 6 tình huống synthetic và 2 reports: [LIVE_PROVIDER_REPORT.md](LIVE_PROVIDER_REPORT.md). Đã thêm 10 kịch bản, gồm transcript 43 turns qua hai map thật: [EXTENDED_LIVE_REPORT.md](EXTENDED_LIVE_REPORT.md). Tiếp tục corpus thực tế và thêm tình huống adversarial; không coi mẫu nhỏ là accuracy tổng quát.
3. Thử setup sạch trên Windows khác, native toolbar side panel, outage 20 giây, reload/navigation và Chrome restart; ghi phần RAM mất/persistent interrupted đúng.
4. Benchmark corpus dự án thật và latency provider dài hạn. Đã có n/median/p95/usage trên mẫu synthetic nhỏ; chưa chứng minh SLA.

## Commands

```powershell
.\scripts\test.ps1 -Browser
.\.venv\Scripts\python.exe scripts\benchmark.py --semantic
.\.venv\Scripts\python.exe scripts\documentation.py
.\.venv\Scripts\python.exe scripts\check_docs.py
```

Các giới hạn khác: [LIMITATIONS.md](LIMITATIONS.md). Đặc tả gốc: [spec/ACCEPTANCE_SPEC.md](spec/ACCEPTANCE_SPEC.md).

Provider review: 6 mẫu đã đối chiếu; key đã xóa khỏi RAM backend sau thử. Meet thật vẫn NOT TESTED.

Expanded provider review: 10 mẫu mới, 6 reports; suggestion median 2.67 s, max 3.93 s. [EXTENDED_LIVE_REPORT.md](EXTENDED_LIVE_REPORT.md). Kết quả theo fixture có giới hạn, không phải SLA.

Latency optimization: cùng 10 fixture median 2.674 → 1.498 s; n=16 median 1.520 s, max 3.399 s. Full validation trước publish, warm client; không phải hard SLA. [LATENCY_REPORT.md](LATENCY_REPORT.md).

Response routing: backend/UI và API preview đã triển khai; xem [RESPONSE_ROUTING.md](RESPONSE_ROUTING.md) và [offline routing review](evidence/routing-review.json). Bộ quy tắc chưa có accuracy corpus thật; số đo latency/provider phía trên là lịch sử trước routing. Ba probe gốc đã bị chặn trong phạm vi giai đoạn 1; chưa có semantic entailment tổng quát.

Giai đoạn 1: [kết quả A–E và giới hạn](PHASE1_REPORT.md); evidence cũ giữ nguyên, các check automated ở bảng trên dùng evidence mới. Provider/latency trước sửa là lịch sử. Không phải MVP VERIFIED.

Phase 2: [capture/recovery/latency, before-after và gate A–G](PHASE2_REPORT.md). Kết quả tự động 228 backend / 56 frontend / 4 browser; Meet thật NOT TESTED, không có paid provider call mới. Số đo lịch sử phía trên không phải benchmark Phase 2.

Phase 3: **PARTIAL** theo mục tiêu đặt trước. [Báo cáo A–F và benchmark đối chiếu](PHASE3_REPORT.md). 39/39 eligible đã có attempted generation, 0 missed/false trigger; logical 49 → 40 (giảm 18,37%, chưa đạt 20%); Auto đợi manual có thể 2,9 s (chưa đạt 500 ms mọi câu ngắn). Không suy ra chất lượng trả lời thật hoặc SLA. Regression 276 backend / 58 frontend / 5 browser. Meet/provider thật mới NOT TESTED; paid calls mới = 0.

Phase 4: **PARTIAL** · [A–F, schema/states, corpus và giới hạn](PHASE4_REPORT.md). 23 synthetic scenarios (5 held-out), 38/38 expected items/evidence; pipeline dài 321 turns/16 maps giữ cancellation và deadline mới. Không là accuracy/model-quality thật. Regression 331 backend / 60 frontend / 6 browser. Meet/model thật NOT TESTED, paid calls mới = 0.

