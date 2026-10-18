# REQUIREMENTS — Yêu cầu sản phẩm

Phiên bản: 1.1 · Ngày: 2026-10-11 · Trạng thái: đặc tả, ứng dụng chưa triển khai.

Tài liệu này chốt hành vi, phạm vi và mức ưu tiên. UI và thiết kế kỹ thuật phải đáp ứng các REQ dưới đây; task và kiểm tra phải trỏ về REQ.

[REQUIREMENTS.md](REQUIREMENTS.md) · [UI_UX_SPEC.md](UI_UX_SPEC.md) · [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md)

## 1. Mục tiêu và người dùng

Trong lúc họp:

1. Thấy khách vừa nói gì và ý nghĩa tiếng Việt.
2. Thấy thông tin liên quan trong ticket, tài liệu, source code hoặc dữ liệu đã nhập.
3. Có câu tiếng Anh ngắn, dễ nói, đúng căn cứ.
4. Có gợi ý hỏi lại khi thông tin chưa rõ.
5. Giữ câu đang đọc đứng yên khi khách tiếp tục nói.

Sau họp:

1. Có bản tóm tắt có thể sửa.
2. Phân biệt yêu cầu, quyết định đã xác nhận, đề xuất và câu hỏi chưa giải quyết.
3. Có action item với người phụ trách/deadline nếu hội thoại thực sự nêu.
4. Mở lại nguồn của từng kết luận và copy/xuất báo cáo.

Đây là trợ lý gợi ý cho người dùng. MVP không tự phát ngôn, gửi chat Meet, gửi email, sửa ticket, sửa code hoặc thực thi câu lệnh theo lời khách.

## 2. Quyết định đã chốt

- Google Meet captions → extension DOM adapter → backend local → truy xuất nguồn → AI văn bản → gợi ý/báo cáo.
- Developer Việt Nam giao tiếp khách global; hiểu ý bằng tiếng Việt, trả lời tiếng Anh đơn giản A2–B1.
- Windows/Chrome desktop, một người dùng, một cuộc họp active.
- Repo/docs/ticket/schema/export nhập local là snapshot. Các nguồn được truy xuất bằng keyword và semantic local khi bật.
- Năm màn hình: Project, Live, Report, History, Settings.
- Codex triển khai ứng dụng chạy được, có giao diện và backend thật; fixture/mock là chế độ demo có nhãn.

## 3. Phạm vi và độ ưu tiên

| Ưu tiên | Hạng mục |
| --- | --- |
| P0 | Capture phụ đề thật; sửa partial; chống trùng; trạng thái capture chính xác; side panel; backend và lưu phiên |
| P0 | Nhập dự án; tìm đúng nguồn; tạo gợi ý có căn cứ; giữ câu đang đọc; báo cáo có bằng chứng |
| P0 | Khởi động Windows; xử lý mất kết nối; dữ liệu giữa các dự án không lẫn; API key ở backend |
| P1 | Embedding local đa ngôn ngữ; nhập CSV/JSON ticket; glossary; xuất Markdown/JSON |
| P1 | Tìm lịch sử; chính sách lưu; xóa dữ liệu; đo latency/token |
| P2 | Jira/GitHub/Notion connector trực tiếp; PDF/DOCX; query DB sống có kiểm soát; đóng gói installer |

**Hoàn thành MVP gồm P0 và P1.** Các mốc đầu được phép chưa bật embedding để kiểm chứng luồng trước. P2 có thể để extension point và tài liệu, không làm tính năng giả trông như đã kết nối.

Không thêm STT trả phí, Whisper, thu audio, microphone, TTS, bot tham gia Meet, OCR hoặc cloud hosting vào MVP. Muốn đổi nguồn phụ đề phải ghi lý do và đề xuất riêng; không tự âm thầm thay quyết định đã chốt.

P0 là yêu cầu phải có để dùng luồng chính đúng. P1 hoàn thiện MVP đã chốt. P2 là giai đoạn sau, không được giao diện giả là đã tích hợp. Thiếu môi trường Meet/provider/Windows không làm ngừng phần độc lập; trạng thái nghiệm thu của phần thiếu vẫn là NOT TESTED.

## 4. Danh mục yêu cầu có mã

| ID | Ưu tiên | Yêu cầu | Hành vi bắt buộc |
| --- | --- | --- | --- |
| REQ-01 | P0 | Chạy local trên Windows/Chrome | Một người dùng, một phiên active; setup không bắt buộc Docker/GPU. |
| REQ-02 | P0 | Dùng phụ đề Meet | Caption DOM là đầu vào; không thu audio hoặc thêm STT vào MVP. |
| REQ-03 | P0 | Caption không trùng/sai revision | Upsert partial, giữ phủ định/số, không loại câu thật lặp lại. |
| REQ-04 | P0 | Trạng thái và khoảng thiếu | Phân biệt im lặng với capture lỗi khi đủ tín hiệu; unknown và gap được hiển thị. |
| REQ-05 | P0 | Phiên đúng tab/project | Bind một tab/document; khóa project; pause/resume/end idempotent; interrupted rõ. |
| REQ-06 | P0 | Phục hồi transport | ACK/retry idempotent, revision monotonic, outbox có giới hạn; đóng panel vẫn capture. |
| REQ-07 | P0 | Nhập dữ liệu dự án | Repo local, docs text, SQL schema/paste và ticket CSV/JSON có preview/mapping; không thực thi. |
| REQ-08 | P0 | Đồng bộ đúng phiên bản | Incremental hash; publish index atomically; lỗi giữ bản tốt cũ; nguồn xóa không còn được tìm. |
| REQ-09 | P0 | Cách ly dự án | Mọi retrieval/cache/source snapshot gắn đúng project/session; ID ticket trùng không gây lẫn. |
| REQ-10 | P1 | Tìm kiếm keyword và semantic | FTS5 baseline; glossary; E5 CPU khi bật; fallback có nhãn; benchmark corpus mẫu. |
| REQ-11 | P0 | Nguồn kiểm tra được | Citation backend cấp; excerpt/path/dòng/version/thời điểm; phân biệt snapshot với nguồn mới. |
| REQ-12 | P0 | Gợi ý dễ hiểu, dễ nói | Nghĩa Việt và 1–3 câu Anh A2–B1; ưu tiên ngắn, đúng ý. |
| REQ-13 | P0 | Không bịa hoặc tự cam kết | Giữ phủ định; status/estimate/deadline thiếu phải hỏi lại; nguồn mâu thuẫn có nhãn. |
| REQ-14 | P0 | Output AI được validate | Schema đúng, source/segment thuộc tập cấp, lỗi có trạng thái; preview chưa validate có nhãn. |
| REQ-15 | P0 | Gợi ý mới và chi phí có kiểm soát | Throttle/debounce, latest queued job, cancel, giới hạn context/request; stale không ghi đè. |
| REQ-16 | P0 | Giữ câu đang đọc | Card được khóa trong khi capture chạy; gợi ý mới có badge để người dùng chuyển. |
| REQ-17 | P0 | Điều khiển AI thủ công | Hỏi AI, chọn đoạn, ngắn hơn/giải thích/hỏi lại/copy; action dùng snapshot card hiện tại. |
| REQ-18 | P0 | Đủ năm màn hình | Project, live, report, history, settings có dữ liệu backend và các trạng thái lỗi/rỗng/loading. |
| REQ-19 | P0 | Báo cáo có bằng chứng | Tách yêu cầu/quyết định/action/câu hỏi/đề xuất; không dùng gợi ý AI làm lời người dùng đã nói. |
| REQ-20 | P0 | Owner/date có xác nhận | Chưa nói rõ thì null/chưa xác nhận; giữ raw date và timezone; phủ định không thành action. |
| REQ-21 | P0 | Báo cáo dài và phiên bản | Xem xét cả transcript dài; edit/save/regenerate giữ phiên bản user edit, conflict được xử lý. |
| REQ-22 | P1 | Lịch sử và xuất | Filter project/ngày/từ khóa; tìm transcript; copy/export Markdown và JSON. |
| REQ-23 | P0 | Key và pairing đúng chỗ | LLM key chỉ backend env/RAM; pairing riêng; REST/WS auth và origin/host validation. |
| REQ-24 | P0 | Lưu/xóa có policy | Local persistence hoặc memory mode; retention 30 ngày cấu hình được; xóa dữ liệu phụ thuộc. |
| REQ-25 | P0 | Khởi động và demo rõ ràng | PowerShell setup/start/build, lockfile, hướng dẫn Chrome unpacked; mock luôn có nhãn. |
| REQ-26 | P1 | Đo thời gian và usage thật | Capture/ACK/retrieval/AI/report timings; request/token; giá ước tính có ngày, unknown không bịa. |
| REQ-27 | P0 | DB là snapshot trong MVP | Schema/export là đầu vào, không claim dữ liệu prod sống; live query/connector thuộc P2. |
| REQ-28 | P0 | Provider lỗi/timeout/cancel rõ | Lỗi thật, retry giới hạn, không fake success hoặc tạo request trùng âm thầm. |
| REQ-29 | P0 | Nguồn và nội dung không chạy lệnh | Repo root/path/size allowlist; skip secret/binary; chống prompt injection; MVP không execution/write tool. |
| REQ-30 | P0 | Bàn giao truy vết và bằng chứng | Requirement nối task/check; kết quả PASS/FAIL/NOT TESTED có môi trường; live thiếu ghi rõ. |

## 5. Kịch bản người dùng và ranh giới thành công

| Journey | Trigger → kết quả | REQ |
| --- | --- | --- |
| Chuẩn bị dự án | Tạo project → nhập nguồn → thấy nguồn ready hoặc lỗi thật → kiểm tra truy xuất | REQ-07, REQ-08, REQ-09, REQ-10, REQ-11 |
| Bắt đầu cuộc họp | Bật caption trong Meet → chọn project → Start → thấy trạng thái capture và caption mới | REQ-02, REQ-03, REQ-04, REQ-05 |
| Trả lời khách | Turn ổn định → hiểu ý → đối chiếu nguồn → câu Anh ngắn; thiếu nguồn thì hỏi lại | REQ-12, REQ-13, REQ-14, REQ-15 |
| Đọc gợi ý | Giữ card → khách tiếp tục → card cũ đứng yên, badge báo mới → chủ động chuyển | REQ-16, REQ-17 |
| Kết thúc | End → flush/ACK hoặc cảnh báo gap → report draft → sửa và xuất | REQ-05, REQ-19, REQ-20, REQ-21, REQ-22 |
| Lưu và phục hồi | Close panel/reconnect/restart → phục hồi đúng theo persistence mode và khoảng thiếu | REQ-06, REQ-24 |

## 6. Hành vi không được suy đoán

- Có source code không đồng nghĩa chức năng đang deploy production. Repo/schema/export có thời điểm snapshot.
- Tên người nói trong caption là label hiển thị; không xác minh danh tính. Không biết ai là Tôi thì hiện ambiguity.
- Stable caption là heuristic, không phải final chính thức; late revision có thể thay nghĩa.
- Im lặng không đồng nghĩa mất caption; không đủ tín hiệu thì unknown.
- Gợi ý AI chưa chắc đã được người dùng phát ngôn. Report lấy bằng chứng từ transcript.
- “Maybe Friday” không thành due đã chốt; “we” không thành owner cụ thể; “not deploy” không thành action deploy.
- “Tìm được citation ID hợp lệ” chỉ chứng minh nguồn tồn tại. Claim vẫn phải được kiểm tra nghĩa qua excerpt/cases.

## 7. Chính sách hoàn thành và thay đổi

MVP hoàn thành khi P0 + P1 được triển khai và nghiệm thu phù hợp, gồm capture Meet thật và provider thật. Chỉ fixture/mock chạy được thì là demo/implementation awaiting live validation. Có failure P0 thì không báo “MVP đã nghiệm thu”.

Đổi dữ liệu đầu vào, tự động gửi thông điệp, live production DB, cloud hosting hoặc thu audio là thay phạm vi; cập nhật yêu cầu theo chỉ đạo người dùng trước khi gọi đó là một phần đã chốt. Quyết định triển khai thường lệ trong phạm vi Codex tự xử lý.

Mỗi thay đổi hành vi ghi REQ bị ảnh hưởng, UI/technical contract, task và check cần cập nhật. Không tăng phần trăm hoàn thành chỉ từ số dòng code hoặc số checkbox.

Bảng nối đầy đủ: [TRACEABILITY.md](TRACEABILITY.md). Tài liệu gốc nằm trong reference để xem lịch sử quyết định, không dùng nó làm task checklist thay cho bộ v1.1.

