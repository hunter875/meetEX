# Contracts triển khai so với bộ đặc tả 1.1

Các thay đổi trong phạm vi yêu cầu; spec gốc được giữ nguyên trong `spec/`. OpenAPI trong `openapi.json` và TypeScript sinh từ nó là hợp đồng executable.

| Phần | Quyết định triển khai |
| --- | --- |
| DOM adapter | `meet-calibrated-v1`, profile tạo từ DOM người dùng chọn; không ship selector Meet chưa quan sát. Live gate chưa đóng. |
| Nguồn upload | File picker đọc UTF-8 nghiêm ngặt, gửi `pasted_text` JSON; local repo/file qua `local_path`. Không multipart/unzip. Preview `/sources/preview`; add/reindex trả job sau khi xử lý, không giả ready. |
| Memory | PATCH meeting `confirmed_segment_ids`; chỉ transcript cùng phiên. Prompt giữ tối đa 8 đoạn nguyên văn trong budget 3.000 ký tự. Revision làm đổi text sẽ bỏ xác nhận cũ. |
| Report evidence | Bổ sung `summary_segment_ids` cho tổng quan; từng item vẫn có evidence, origin, confirmation. Save tạo version mới và dùng expected_version trên latest version. |
| Source drawer | `/sources/{id}/chunks` cho current excerpts; `/meetings/{id}/suggestions/{sid}/citations` cho immutable request excerpts + source_changed/source_deleted. Model không cấp path/link. |
| Job orchestration | Cache theo snapshot hash/action/question trong cùng meeting/project; một active + latest queued. Auto không thay queued manual; manual cancel upstream cũ. |
| Xóa | Event `meeting.deleted` gửi ID để xóa browser RAM cache; reconnect đối chiếu meeting IDs. Source delete giữ historical excerpts tới khi xóa meeting/project. |
| Capture diagnostics | Bổ sung unknown, adapter heartbeat, `adapter_heartbeat_lost` và `interrupted_pending_discarded`. Không nâng unknown thành captions_off. |
| Timings | Caption event → ACK đo clock monotonic trong content script, RAM samples. Backend đo apply/retrieval/provider first token/stable→request/validated/report bằng clock cùng process. |
| Budget | Live JSON context tối đa 18.000 ký tự, output provider 800 tokens; report map output 6.000 tokens. Input token estimate chưa là tokenizer DeepSeek chính xác. |

API key: env hoặc RAM backend; response settings chỉ có has_key. Pairing token local riêng; REST Bearer, WS auth frame đầu, Origin exact, Host loopback. `.env.example` không có secret. UI backend URL chỉ localhost/127.0.0.1 cổng 8765 theo manifest CSP/host permissions.

Nguồn xác minh: [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/), [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/), [E5 model card](https://huggingface.co/intfloat/multilingual-e5-small), [SQLite FTS5](https://www.sqlite.org/fts5.html), [Python zoneinfo](https://docs.python.org/3/library/zoneinfo.html), [Playwright extension testing](https://playwright.dev/docs/chrome-extensions). Docs xác nhận cấu hình/provider protocol, không thay test account/Meet thật.

## Response routing bổ sung

SuggestInput thêm response_mode (auto/fast/explain/deep/clarify, mặc định auto); POST meetings/{id}/classify trả RoutingDecision mà không schedule provider. AISnapshot.routing nullable cho lịch sử cũ; request Auto có thể có status skipped. Metrics thêm classifier, provider_by_route và route trên provider record. Client không truyền routing. Cache bỏ classifier_ms khỏi hash; vẫn giữ route/policy version trong hash. Xem [RESPONSE_ROUTING.md](RESPONSE_ROUTING.md). OpenAPI và TypeScript được tạo lại cùng thay đổi.

## Giai đoạn 1 — hành vi đúng đắn, không đổi schema

Không thêm field output/API/event hoặc đổi DTO; OpenAPI và TypeScript kiểm tra khớp, không sửa generated types bằng tay. Client cũ tiếp tục đọc dữ liệu/snapshot/report cũ. Các kết quả cũ không được tự tái chứng nhận bằng validator mới.

Create/resume dùng cùng slot active/paused trên disk/RAM, lock một process/worker từ check đến commit. Resume xung đột trả 409 ACTIVE_MEETING; chuyển trạng thái không hợp lệ trả 409 INVALID_STATE. Replay cùng idempotency key giữ response lịch sử nhưng không áp dụng lại state hay gap. Không tự kết thúc phiên khác.

Các lỗi guard mới dùng cùng error envelope hiện có: AI_NUMERIC, AI_CLAIM, AI_UNVERIFIED; REPORT_NUMERIC, REPORT_CLAIM, REPORT_TASK, REPORT_PROPOSAL. AI_COMMITMENT/REPORT_DUE được siết theo task. Schema/ID/revision, routing và tối đa một repair vẫn giữ; lỗi cuối không có ready và không thay phiên bản user edit. Proposal không được gán confirmed/owner/deadline như fact.

Input hash có salt nội bộ `bounded-evidence-v1`; timing không tham gia hash. Không tái dùng cache được duyệt bằng policy trước. Trích dẫn vẫn trỏ ID gốc; số liệu dùng excerpt thật, cam kết dùng các turn hỗ trợ được model cite trong snapshot. [Chi tiết phạm vi và evidence](PHASE1_REPORT.md).

## Phase 2 — capture và timing

`Caption.text` và segment text giữ nguyên whitespace/newline; không đổi field schema. Revision/speaker correction làm stale/bỏ memory confirmation liên quan. Reload document giờ interrupted, đòi Resume và không replay pending của document trước. API control reason `interrupted_pending_discarded` ghi gap khi pause/end bỏ event chưa ACK. Backend chỉ socket capture owner hiện tại được gửi caption/status, scope lỗi trả BINDING_SCOPE.

WebSocket ACK caption thêm segment_id, segment_revision, backend_applied và processing_ms, đều additive. `backend_applied` là kết quả apply/idempotent ACK, không phải timestamp khác clock. capture.gap payload có event_id tùy chọn; client mới lưu/retry tới `capture.gap.ack {protocol_version,session_id,event_id,reason}`; backend dedup qua applied_events. Client cũ không có event_id vẫn hoạt động theo best effort.

SuggestionDTO/AIRequestDTO thêm timing nullable mặc định null cho lịch sử cũ; RequestTimingDTO có trigger, temperature (client cold/warm), retrieval, provider_mode, outcome, marks (stage + offset_ms), provider_ms, validation_ms, stable_to_scheduled_ms optional. Metrics thêm latency_records RAM bounded 1000, gồm thất bại/cancel/supersede; không có transcript/key/token. OpenAPI và generated TypeScript đã tạo lại, contract check pass. Duration cùng perf_counter process, không so clock khác nhau.

Extension ui.state thêm capture_diagnostics (backend_connected, content_alive, adapter_status, pending_gap), giữ fields cũ. Session RAM telemetry mới có meeting/event/segment revision/request ID và duration, không text; content clock tương quan chính xác epoch/revision, render notification sau 2 rAF. `captureTimings` cũ giữ emit-event→ACK, không trộn với observed→ACK mới. Xem [Phase 2](PHASE2_REPORT.md).

Các component `CaptionAckDTO`, `CaptureGapAckDTO`, `CaptureDiagnosticsDTO` được export trong OpenAPI cùng request timing và generated TypeScript dù không có HTTP route riêng; UI dùng type diagnostics được sinh. WebSocket/extension fields vì vậy có schema và không phải chỉ prose.
