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
