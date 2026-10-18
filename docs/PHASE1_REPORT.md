# Giai đoạn 1 — phiên họp và kiểm tra bằng chứng

Ngày: 2026-10-18 (America/Los_Angeles). Commit nền `cd6b79f876a6d3e00f26801dacfebb10bb87cbfb`, branch ban đầu `main`, working tree sạch; thực hiện trên `codex/phase1-correctness`. Không thay đổi spec gốc, không gọi provider trả phí, không tạo Meet thật hoặc gửi nội dung cho người khác. Đây không phải MVP VERIFIED.

## Kết quả A–E

| Mục | Kết quả | Bằng chứng và phạm vi |
| --- | --- | --- |
| A — tối đa một active/paused | PASS | Lock chung cho create/control trên local và RAM; 409 ACTIVE_MEETING khi resume tranh slot; HTTP, đủ bốn cặp persistence, paused/active, ended, replay và ba kiểu cạnh tranh được kiểm tra |
| B — số liệu với citation | PASS trong phạm vi đã hỗ trợ | Đối chiếu thuộc tính/thực thể/đơn vị/phủ định/khoảng/điều kiện từ excerpt gốc; không lấy TTL thay timeout; không suy thuộc tính từ một số trần trong nguồn |
| C — nhận đúng task | PASS trong phạm vi đã hỗ trợ | Hành động + đối tượng + môi trường + người nhận; không dùng khả năng/câu hỏi/participant khác/phủ định làm chấp nhận; hỗ trợ các alias được khai báo |
| D — đúng mệnh đề xác nhận | PASS trong phạm vi đã hỗ trợ | Kiểm tra cả summary và item, cả hai trường ngôn ngữ; staging không cấp quyền production; owner/deadline phải khớp task; pending không tự thành decision confirmed |
| E — pipeline | PASS | HTTP → SSE adapter thật với MockTransport → guard → tối đa một repair → API/store/event. Sai không ready, sửa đúng được nhận, sửa sai dừng; per-map và sau merge đều kiểm tra, user version được giữ |

PASS của B–D không có nghĩa đã có bộ entailment tổng quát. Đây là các mẫu có cấu trúc/alias trong phạm vi dưới đây, được thử với dữ liệu synthetic.

## Tái hiện trước sửa và hành vi sau sửa

Baseline chạy trước thay đổi: backend **91 pass**, frontend **13 pass**. Không chạy riêng typecheck/build/browser/contract trước sửa; các bước đó được chạy sau sửa. [Bốn regression trước sửa](evidence/phase1/before-fixes.xml) đều FAIL như dự kiến: ba validator không raise và HTTP resume trả 200. Không sửa expected để che lỗi.

| Trước sửa | Sau sửa |
| --- | --- |
| Interrupt A, tạo B, resume A → hai active | 409 ACTIVE_MEETING; A/B và dữ liệu/binding không đổi; khi B ended, A resume được |
| Timeout 15 s, finding 90 s trích đúng ID → chấp nhận | AI_NUMERIC; cùng số 90 trong TTL hoặc endpoint khác không hợp thức hóa claim |
| Nhận review CSV → hứa rewrite auth → chấp nhận | AI_COMMITMENT; muốn hứa phải trỏ turn chấp nhận và khớp đúng task |
| Confirmed staging, production pending → report duyệt production | REPORT_CLAIM, kể cả lỗi chỉ nằm ở summary hoặc text_en |
| Cache cũ chỉ theo context/model | Hash thêm phiên bản validation policy; không tái sử dụng kết quả được duyệt bằng policy trước |

Các response idempotency đã ghi vẫn được replay nguyên trạng mà không áp dụng lại transition. Vì vậy replay có thể trả snapshot lịch sử active trong khi state hiện tại interrupted; nó không chiếm lại slot. Một worker/process vẫn là giới hạn bắt buộc.

## Phạm vi semantic validation

Số liệu: prose có nhãn timeout, cache TTL, retry count, upload limit, HTTP status. Thời gian chuẩn hóa Decimal giữa milliseconds/ms, seconds/s/sec/giây, minutes/min/phút; size giữa byte/bytes, MiB và MB. Có test tương đương ms↔s, s↔minute, MiB↔bytes và phân biệt MiB/MB. Không tuyên bố hỗ trợ mọi đơn vị, định dạng số theo locale hoặc mọi key JSON/code.

Đối chiếu giữ thuộc tính, ID dạng API-/SVC- và path /vN/ nhận diện được, môi trường, phép so sánh, range, phủ định và điều kiện. Một giá trị tentative/proposed/alternative không thành giá trị chắc chắn. Chỉ chuẩn hóa điều kiện theo từ/alias hỗ trợ, không dịch được mọi cách diễn đạt điều kiện. Nguồn có số nhưng không gắn được thuộc tính không chứng minh một tham số mới. Trích nguyên văn có thể được giữ nguyên; không suy thuộc tính khác từ câu trích.

Task: nhóm động từ/alias trong `evidence.py` gồm review/inspect/examine, investigate/look into, rewrite, test, deploy/release, fix, share/send, implement/build, preserve, escape, choose và các alias Việt đã khai báo. So khớp đối tượng/chi tiết/môi trường, không cấp quyền theo một câu “I will” bất kỳ. “I can” chỉ là khả năng, không được dùng làm bằng chứng nhận việc. Cam kết có điều kiện/phép quy chiếu không phân giải được sẽ bị chặn và cần hỏi lại; chưa có coreference hay bộ nhớ dài hạn.

Decision/owner/date: confirmation chỉ có hiệu lực trong mệnh đề phù hợp, không truyền qua câu/contrast khác. Owner cần lời nhận của đúng speaker hoặc mệnh đề giao việc được xác nhận, không chỉ tên xuất hiện. Ngày được lấy trong phần task đã khớp, không mượn task bên cạnh. Ngày tương đối vẫn là raw text, không tự đổi thành ISO. Summary và text/text_en đều được kiểm tra; `user_edit` được giữ theo chính sách chỉnh sửa hiện có.

Finding định tính muốn mang nhãn supported phải nằm trong phạm vi trích nguyên văn/lexical aliases đã kiểm tra. Paraphrase không nhận diện được bị AI_UNVERIFIED; repair phải bỏ finding hoặc ghi rõ partial, không tự gán supported. Điều này có thể bảo thủ. Reply định tính thông thường không bị ép thành câu hỏi nếu không có dấu hiệu cần kiểm chứng. Đề xuất số mới được phép khi ghi rõ là đề xuất và không khẳng định giá trị hiện tại/đã duyệt; proposal report không được mang owner/deadline/confirmed như fact.

Chưa bảo đảm mọi định tính, suy luận nhiều bước, câu dẫn dắt, phủ định lồng nhau, viết tắt mới, đổi thứ tự phức tạp, named entity tùy ý hoặc bản dịch tự do đều đúng. “Passed validation” chỉ là đã qua các kiểm tra có giới hạn, không phải chứng nhận độ đúng của cả câu trả lời. Các trường hợp chưa xác minh cần hỏi lại/partial/unconfirmed và người dùng xem lại.

## File và hàm chính

- `storage.py`: `ensure_session_slot`, `create_meeting`, `control`; RLock giữ từ kiểm tra đến commit, dùng chung disk/RAM.
- `evidence.py`: tách trích xuất `quantities`/`tasks`, chuẩn hóa đơn vị/alias, đối chiếu `same_quantity`/`same_task`, kiểm tra cam kết/mệnh đề/owner/date.
- `llm.py`: `validate_suggestion`, `validate_report`, hướng dẫn giữ attribute/task và cite turn nhận việc; không đổi output schema.
- `service.py`: `prepare` thêm policy vào hash; `generate_suggestion` sửa có giới hạn cho lỗi semantic mới. Report map/merge dùng validator mới qua pipeline hiện có.
- `test_phase1_sessions.py`, `test_phase1_semantics.py`, `test_phase1_pipeline.py`, `semantic_cases.py` và fixture 82 case.
- `evaluate_phase1.py`: đếm false accept/reject riêng, chạy lại ba probe gốc, ghi environment/base commit/source hashes. E2E thêm lựa chọn thư mục evidence để không ghi đè lịch sử.

## Kiểm tra thực chạy

| Kiểm tra | Kết quả | Evidence |
| --- | --- | --- |
| Baseline backend/frontend | 91 / 13 pass | baseline-backend.xml, baseline-frontend.json |
| Backend cuối | 219 pass; một warning deprecation Starlette có từ baseline | backend-final.xml, backend-final.log |
| Session recheck với binding/caption thật trong fixture | 18 pass, không cộng trùng vào tổng backend | sessions-final.xml |
| Frontend unit | 13 pass | frontend-final.json |
| TypeScript + extension build | PASS | typecheck.log, build.log |
| OpenAPI/TypeScript contract | PASS, không thay schema | contracts-final.log |
| Ba probe gốc | 3/3 bị chặn | semantic-review.json |
| Browser E2E | 3 pass; MV3/backend thật, DOM/AI synthetic | browser-final-results.json, browser-final.log |

Tất cả đường dẫn trong bảng thuộc [evidence/phase1](evidence/phase1). Bằng chứng trước sửa và các lượt lỗi trung gian được giữ riêng; lỗi harness HTTP 201/schema proposal cũng được sửa để khớp contract, không sửa hành vi mong muốn. Evidence lịch sử ngoài thư mục này không bị ghi đè.

| Nhóm fixture | Câu đúng | Câu sai | Sai bị lọt | Đúng bị chặn |
| --- | --- | --- | --- | --- |
| Numeric/grounding | 15 | 25 | 0 | 0 |
| Task | 6 | 10 | 0 | 0 |
| Decision/assignment/date | 7 | 19 | 0 | 0 |

Tổng 82 case: 28 positive, 54 negative. Không gọi tỷ lệ fixture này là accuracy họp thật. [JSON review](evidence/phase1/semantic-review.json) ghi từng case và code lỗi.

Lệnh đã dùng (từ gốc repo, frontend chạy trong extension):

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q --junitxml=docs/evidence/phase1/backend-final.xml
.\.venv\Scripts\python.exe scripts/evaluate_phase1.py
# Trong extension:
node ../node_modules/vitest/vitest.mjs run --maxWorkers=1 --minWorkers=1 --reporter=default --reporter=json --outputFile=../docs/evidence/phase1/frontend-final.json
# Từ gốc:
npm run typecheck
npm run build
npm run contracts
$env:MEET_E2E_EVIDENCE_DIR='docs/evidence/phase1/browser-final'
$env:PLAYWRIGHT_JSON_OUTPUT_FILE='docs/evidence/phase1/browser-final-results.json'
npx playwright test --reporter=list,json --output=test-results/phase1-final
```

## Giai đoạn 2 và gate còn mở

Mở rộng corpus/ngôn ngữ/grammar và đo false accept/reject trên dữ liệu thực được phép dùng; cải thiện grounding định tính/coreference và kiểm tra bản dịch. Sau đó mới làm bảng phương án có trọng số hoặc bộ nhớ quyết định dài hạn theo phạm vi được chốt. Connector, installer và cloud hosting không được triển khai trong giai đoạn này.

Meet thật, họp hàng giờ, outage thực tế, Windows sạch, chất lượng provider thật và latency sau sửa vẫn NOT TESTED trong giai đoạn này. Không hạ guard để giữ số đo 1,5 giây cũ.

[Manifest môi trường, lệnh, exit code và artifact](evidence/phase1/verification.json).
