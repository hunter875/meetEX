# Phase 2 — capture, recovery và latency

Ngày phía client: **2026-10-18**, America/Los_Angeles. Đầu vào: nhánh `codex/phase1-correctness`, commit `c81a95b1c24726a1b1ebaa309bdd5d6890cb3833`, working tree sạch; thực hiện trên `codex/phase2-capture`. Không có AGENTS.md trong repository/các thư mục cha đã kiểm tra. Giữ nguyên spec gốc và evidence Phase 1. GitHub CLI xác nhận repository hiện PUBLIC; mô tả private cũ ở README đã được sửa, không thay đổi visibility.

**Implementation và kiểm thử độc lập đã hoàn tất; live validation pending. Không phải MVP VERIFIED.** Không gọi provider trả phí, không tham gia/gửi tin vào meeting, không thu audio. Browser dùng Chromium 141.0.7390.37 trên Windows 11, Python 3.13.4, Node 22.20.0. SSE provider được `httpx.MockTransport` chặn trong fixture server; field `provider_mode=real` ở metrics chỉ nhánh code Provider, không chứng minh gọi model thật trong lần thử này.

## A–G

| Phần | Kết quả | Phạm vi / phần còn thiếu |
| --- | --- | --- |
| A · partial/revision/turn | PARTIAL | Replay synthetic qua reducer sản phẩm đạt; raw text, số/negation/revision được giữ. Ranh giới lượt nói vẫn là heuristic, không phân biệt được mọi trường hợp giống hệt trên cùng node không có lifecycle signal. |
| B · DOM replacement/scrolling | PARTIAL | Node thay và cửa sổ block/text có replay; match giới hạn và gap khi mơ hồ. Không có DOM/profile Meet thật để chứng minh mọi kiểu window/correction. |
| C · speaker/tab/document/meeting | PASS trong automated scope | Sender + tab/document/path, label tới muộn, socket owner hiện tại, tab thứ hai, reload và text chứa tên/newline đều có test. Label không xác minh danh tính. |
| D · controls/recovery | PASS trong automated scope | Worker thật qua outage proxy 5/20 s, ACK retry/idempotency, restart worker, local/RAM backend restart, reverse revision, overflow, pause/resume/end. Không thay nghiệm thu mạng/Meet thật. |
| E · trạng thái capture | PASS trong automated scope | Selector mất → unsupported; root mất → unknown; im lặng → waiting; explicit toggle → off. Backend/content/adapter/pending tách riêng trong UI. |
| F · đo đầu cuối | PARTIAL | Đo cùng clock cho observed→ACK và notification sau render, backend provider/validation riêng; có ready/stale/error/cancelled, manual/auto và cold/warm client. Chưa có provider thật, semantic latency mới, hoặc speech/pixel ground truth. |
| G · Meet thật | NOT TESTED | Chưa có hai participant trong môi trường được phép. [Runbook, recorder, form và bước người dùng cần làm](PHASE2_LIVE_RUNBOOK.md). |

## Baseline và lỗi trước → sau

Baseline: **219 backend / 13 frontend** pass. Regression một active/paused gồm disk/RAM và ba probe sai nghĩa vẫn bị chặn. [Semantic regression hiện tại](evidence/phase2/semantic-regression.json) có 82 fixture, false accept/reject đều 0 trong corpus, không phải accuracy tổng quát. Không sửa validator để làm capture pass; `evidence.py` và semantic rules trong `llm.py` không đổi.

Replay ban đầu bắt **8 lỗi sản phẩm / 18 case**. [Raw trước sửa](evidence/phase2/replay-before.json) giữ cả lỗi harness: positive control lần đầu chọn nhầm case phủ định vốn đã pass. Sau đó chọn nguyên case numeric đang fail, dùng nguyên reducer cũ trong `extension/tests/legacy` và assert nó không đạt expected. Không đổi expected để bỏ chữ/số/lượt nói.

| Lỗi trước sửa | Hành vi sau sửa |
| --- | --- |
| Stable “Timeout 15.5 ms API-17” → “Timeout 50.5 ms API-71” thành hai đoạn | Cùng node/speaker và lexical anchors → cùng ID, tăng revision, giữ nguyên giá trị mới |
| “yes” → “Yes!” tách turn | Comparison key phục vụ match, raw casing/punctuation vẫn cập nhật cùng ID |
| Node thay đồng thời turn cũ cuộn khỏi slot trước | Match duy nhất trong các node vừa mất, độc lập chỉ số slot; node còn hiện không bị mượn |
| Node recycle khi partial chưa stable ghi đè câu không liên quan | Finalize câu cũ, tạo ID mới; possible gap cho ranh giới mơ hồ |
| Speaker null rồi có tên tạo đoạn thứ hai | Bổ sung label trên cùng ID/revision; không suy label từ nội dung câu |
| Reducer và SQLite gộp whitespace/newline | Giữ text gốc ở cả reducer và storage |
| Một node chỉ còn suffix của cửa sổ text làm mất đầu câu | Giữ prefix đã quan sát khi có overlap suffix→prefix đủ dài, trong cùng lifecycle và thời gian giới hạn |
| ACK mất nhưng socket còn sống chỉ gửi lại khi reconnect | Quét retry mỗi 1 s, resend sau ≥2 s bằng chính event ID; backend ACK idempotent |
| Tab reload đổi document nhưng có thể mang pending cũ sang document mới | Interrupted, bỏ pending kèm warning, đòi Resume; prime caption cũ |
| Socket document/connection cũ còn gửi sau bind mới | Backend kiểm tra binding + socket owner hiện tại trước apply |
| Pause có pending được replay khi Resume | Dừng adapter/gate trước control; pending không ACK bị bỏ với reason được ghi trong backend; không lưu đoạn trong pause |
| Toggle off vẫn giữ observer; selector text hỏng thành waiting/observing | Disconnect khi off, cleanup khi stop, selector hỏng → unsupported_dom |
| Gap gửi một lần có thể mất ở reconnect | Gap mới có event ID, lưu session RAM, retry và chỉ xóa sau matching ACK; backend dedup |

## Thiết kế và file/hàm chính

- `extension/src/content/caption-reducer.ts`: `related`, `scrollPrefix`, `CaptionReducer.update/tick/prime`. Không global dedup, không LCS/code bên ngoài. Comparison tối đa 160 whitespace tokens ở tail; không bỏ dấu thập phân, negation hay ID trong text đã phát. Replacement đòi cùng label, node cũ đã mất, match duy nhất, ≥3 tokens và ≤1,5 s kể từ lần thấy; scroll overlap ≥3 tokens, cùng node và ≤3 s. Những ngưỡng này là policy synthetic chưa hiệu chuẩn Meet thật.
- `meet-adapter.ts`: đọc ngay mutation batch đã giao, thay trailing debounce có thể bỏ turn ngắn; watchdog 500 ms, stable tick 100 ms. Chỉ đọc root/profile được chọn; không body/html fallback. Không đọc chat để bù selector lỗi. `stop()` disconnect/timer cleanup, mất root/selector báo đúng trạng thái. Calibration dừng instance cũ, instance mới prime lại.
- `background/index.ts`, `outbox.ts`: giữ event ID, count/UTF-8 byte bounds 500 / 5 MiB, restore bounds có marker; retry, gap ACK, scope calibration, document reload, pause/end pending, current capture diagnostics. Session storage thuộc trusted extension contexts, không ghi outbox vào local/disk. Đóng panel không dừng capture.
- `backend/app/main.py`: ownership WS và ACK correlation (`segment_id`, `segment_revision`, `backend_applied`, `processing_ms`); gap ACK idempotent; trạng thái disconnect được lưu. Client gap cũ không event ID vẫn được chấp nhận một lần, không có reliable gap ACK.
- `backend/app/storage.py`: raw text; speaker correction cũng làm stale card/bỏ xác nhận memory liên quan; control reason ghi mất pending. Một user/một worker vẫn giữ nguyên.
- `content/capture-timing.ts`, `content/index.ts`, `ui/live.tsx`, `ui/api.tsx`: correlation epoch/segment/revision/request, notification sau hai animation frames của card thực sự hiển thị, status/content liveness độc lập backend. Telemetry chỉ ID/duration/status trong session RAM, thêm meeting ID để không gộp các phiên.
- `backend/app/service.py`, `models.py`: request timing từ `perf_counter`, provider/validation/repair outcomes; queued cancelled/superseded cũng được ghi. DTO optional cho lịch sử cũ; OpenAPI/TypeScript sinh lại. Không đưa timing vào cache hash.

Stable là heuristic một giây không đổi, không phải Google final. Correction vẫn có thể cập nhật stable segment. Prefix không còn hiện trong DOM không thể được sửa theo một correction đã hoàn toàn cuộn khỏi cửa sổ. Same-node repeated text không có mutation, batch add/remove xảy ra trọn trong một JS task, short replacement và nhiều ứng viên giống nhau vẫn mơ hồ; có thể cần gap/đoạn riêng và đối chiếu người dùng. Không tuyên bố “không mất/lặp” cho mọi DOM Google chưa quan sát.

## Nguồn tham khảo và license

Đọc phiên bản hiện tại qua shallow clone, không chạy code/dependency của hai dự án:

- [MeetCaptioner commit fa44de48b278a7f73a61bdd0e869a99a5b93e21e](https://github.com/LeHoangTuanbk/MeetCaptioner/tree/fa44de48b278a7f73a61bdd0e869a99a5b93e21e), MIT. Đọc caption-text-alignment, caption-stream-tracker, observer và caption-stream. Học cách bounded alignment và lifecycle element tách khỏi speaker/text. Không dùng ngưỡng của repo đó làm bằng chứng meetEX.
- [meet-live-assist-extension commit c26b04e6eb875a44536bed5afb3e80ce49b56ff1](https://github.com/krystiangw/meet-live-assist-extension/tree/c26b04e6eb875a44536bed5afb3e80ce49b56ff1), `LICENSE.md` PolyForm Internal Use 1.0.0 có hạn chế phân phối. Đọc src/content.js, test/captions.mjs và CHANGELOG về window/casing/punctuation. Không đưa code/thuật toán triển khai có bản quyền của repo này vào sản phẩm; tự viết từ yêu cầu/hành vi, không dùng global sentence dedup của họ vì có thể xóa lượt lặp thật.

## Kiểm thử thực chạy và evidence

Kết quả cuối: **228 backend / 56 frontend / 4 browser** pass, typecheck/build/contracts pass. Backend có một warning deprecation Starlette/anyio có sẵn. Frontend gồm 19 replay tests (18 cases + positive control), 8 DOM tests, 15 worker transport tests, 1 timing test và 13 test cũ. Chín backend tests mới kiểm tra raw/revision/idempotency, control gap, local/RAM restart, obsolete document/gap ACK và timing. Counts không cộng các lượt chạy lặp thành mẫu độc lập.

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -q --junitxml=docs/evidence/phase2/backend-final.xml
node node_modules/vitest/vitest.mjs run --root extension --maxWorkers=1 --minWorkers=1 --reporter=json --outputFile=../docs/evidence/phase2/frontend-final.json
npm run typecheck
npm run build
npm run contracts
$env:MEET_E2E_EVIDENCE_DIR='docs/evidence/phase2/browser-final'
$env:MEET_E2E_RESULTS_FILE='docs/evidence/phase2/browser-final-results.json'
node node_modules/@playwright/test/cli.js test
.venv\Scripts\python.exe scripts/evaluate_phase1.py --output docs/evidence/phase2/semantic-regression.json --base-commit c81a95b1c24726a1b1ebaa309bdd5d6890cb3833 --starting-branch codex/phase1-correctness
.venv\Scripts\python.exe scripts/evaluate_phase2.py
.venv\Scripts\python.exe scripts/documentation.py
.venv\Scripts\python.exe scripts/check_docs.py
```

[Review có source hashes và số đo nhóm](evidence/phase2/review.json), [backend](evidence/phase2/backend-final.xml), [frontend](evidence/phase2/frontend-final.json), [browser](evidence/phase2/browser-final-results.json), [recovery/transcript/telemetry](evidence/phase2/browser-final/phase2-recovery.json). Fixtures đều **synthetic**, không giả là captured DOM/Meet live. E2E dùng proxy test cắt WS, không giả ACK; FastAPI/SQLite và MV3 thật. Outage 5/20 s đều phục hồi transcript đúng ba nội dung mong đợi, outbox về 0, chưa sinh AI request ở đoạn recovery. Sau đó chạy provider adapter/validator giả lập với các outcomes riêng.

Các artifacts `*-first`, `*-candidate*`, `replay-before`, log build lỗi được giữ để phân biệt thử chưa đạt với kết quả cuối. Lỗi harness đã sửa gồm Host header WebSocket, chọn self speaker chưa quan sát, Playwright offline không cắt worker WS, và proxy ghi HTTP headers sau request abort. Một lỗi typecheck nullable binding đã sửa bằng guard rõ ràng. Không hạ validator hoặc expected text để pass.

## Latency và phần chưa đo

Số cụ thể, n/median/nearest-rank p95/max theo manual/auto, cold/warm client, keyword/semantic, ready/stale/error/cancelled ở review và [phần Phase 2 trong LATENCY_REPORT](LATENCY_REPORT.md). Không bỏ failure/cancel khỏi mẫu request; request không có provider/render được đếm riêng. Semantic mới, provider thật và speech→rendered **NOT TESTED**.

- Content clock: observation lúc adapter phát revision, stable lúc heuristic, ACK nhận, schedule notification nhận, notification sau card render. `observed_to_ack_ms` của stable revision tính từ observation của partial tương ứng, gồm thời gian chờ stable. Mảng `captureTimings` cũ đo emit-event→ACK, giữ tương thích và không trộn với metric mới.
- Backend clock: apply duration trong ACK, schedule offset 0, provider started/completed, validation completed và request completed; `stable_to_scheduled_ms` dùng backend arrival of stable, không phải thời gian content stable. `provider_ms` bao quanh Provider.complete, gồm adapter/schema/retry; validation_ms là evidence guard, gồm repair guard và final publication guard.
- `stable_to_schedule_received_ms` gồm giao message từ backend tới content. `card_rendered_notification` gồm hai rAF và message về content, là proxy sau paint opportunity, không đo pixel độc lập. Không trừ clock UI/content/backend với nhau. Error/cancelled không có card để đo rendered; pinned/closed panel có thể không render dù request ready.

## Người dùng cần kiểm chứng và Phase 3

Thực hiện [buổi Meet thử hai participant](PHASE2_LIVE_RUNBOOK.md), ghi DOM captions độc lập và so snapshot, điền [form](../fixtures/phase2/live-result-template.json). Phân loại riêng ASR Google sai và meetEX làm sai caption đã thấy; chỉ chia sẻ bản ẩn danh. Không đóng live gate bằng số đo synthetic.

Phase 3: tối ưu trigger/scheduling, giảm request Auto do revision/stable, gom burst có kiểm chứng, giảm gợi ý lặp và đánh giá UX pause/thinking theo route. Chưa có weighted decision matrix, connector, installer, audio/bot/MCP/cloud hoặc bộ nhớ quyết định dài hạn mới trong Phase 2.
