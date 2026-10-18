# UI/UX SPEC — Năm màn hình và tương tác

Phiên bản: 1.1 · Ngày: 2026-10-11 · Trạng thái: đặc tả, ứng dụng chưa triển khai.

Tài liệu này sở hữu màn hình, điều khiển, user journey và trạng thái UI. Payload/API/DB chỉ tham chiếu TECHNICAL_DESIGN.md.

[REQUIREMENTS.md](REQUIREMENTS.md) · [UI_UX_SPEC.md](UI_UX_SPEC.md) · [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md)

## 1. Bố cục và nguyên tắc

- Side panel dùng trong lúc họp; dashboard tab của extension dùng quản lý và report.
- Dashboard mở được khi chưa vào Meet. Nhấn Live hướng dẫn mở/bind đúng tab Meet thay vì giả có cuộc họp.
- Live khoảng 360–480 px, thử 320 px; chữ rõ, không cuộn ngang. Vùng câu Anh dễ đọc và không tự di chuyển khi giữ card.
- UI chính dùng tiếng Việt; phần câu để nói là tiếng Anh, có nghĩa Việt bên cạnh/dưới.
- Capture status, backend connection và AI state là ba trạng thái riêng. Backend connected không chứng minh caption đang thu hoặc provider hoạt động.
- Dữ liệu giả luôn có banner Demo; số liệu/status dự án không có nguồn không được tự điền.
- Nút thực thi có disabled/loading/error theo action; không hiện Done trước ACK/kết quả phù hợp.

## 2. Danh mục màn hình

| ID | Màn hình và route | REQ chính |
| --- | --- | --- |
| UI-01 | Dự án & dữ liệu: /projects, /projects/:projectId | REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-27, REQ-29 |
| UI-02 | Đang họp: side panel | REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-17 |
| UI-03 | Báo cáo: /meetings/:meetingId/report | REQ-19, REQ-20, REQ-21, REQ-22 |
| UI-04 | Lịch sử: /meetings | REQ-05, REQ-22, REQ-24 |
| UI-05 | Cài đặt: /settings | REQ-01, REQ-10, REQ-15, REQ-23, REQ-24, REQ-25, REQ-26, REQ-28 |

## UI-01 — Dự án & dữ liệu

Route dashboard: /projects và /projects/:projectId.

Có danh sách dự án, tên, mô tả ngắn, glossary, ngôn ngữ, lần cập nhật nguồn gần nhất. Người dùng tạo project và nhập nguồn.

Nguồn MVP:

- Repo folder local đã tồn tại: backend đọc theo đường dẫn do người dùng chủ động thêm.
- Tài liệu .md, .txt; schema .sql được đọc như văn bản.
- Ticket .json/.csv theo mapping ID, title, description, status, updated_at, URL.
- CSV dữ liệu đã xuất: nhập vào dạng nguồn văn bản/bản ghi; giới hạn và xem trước trước khi index.
- Pasted text có tiêu đề và loại nguồn.

Không tự clone repo private hoặc yêu cầu tài khoản Jira trong MVP. Thêm connector sau khi nguồn file/local chạy đúng.

Mỗi nguồn có: loại, tên/path, số file/chunk, trạng thái queued/indexing/ready/error, lần cập nhật, dữ liệu có cũ không. Có Đồng bộ lại, Xem nguồn, Xóa nguồn.

Khi nguồn lỗi, hiển thị lỗi thật; lần index tốt trước vẫn có thể dùng với nhãn cũ. Project rỗng vẫn capture được; phần AI hiện chưa có căn cứ dự án.

## UI-02 — Đang họp

Side panel, thiết kế phù hợp chiều rộng khoảng 360–480 px; kiểm tra ở 320 px. Không có cuộn ngang.

Header:

- Project đã chọn, tên phiên họp.
- Capture status, backend connection, thời điểm nhận caption gần nhất.
- Bắt đầu, Tạm dừng/Tiếp tục, Kết thúc.
- Liên kết mở dashboard.
- Dự án của phiên được khóa sau khi Bắt đầu; đổi dự án bằng phiên mới để tránh lẫn dữ liệu.

Ba vùng chính:

| Vùng | Nội dung |
| --- | --- |
| Khách vừa nói | Caption gần nhất, người nói nếu Meet cung cấp, đánh dấu đoạn đang thay đổi; nút mở toàn transcript |
| Hiểu ý & đối chiếu | Nghĩa tiếng Việt, câu hỏi/yêu cầu chính, thông tin tìm được, nguồn và chỗ cần hỏi lại |
| Câu trả lời gợi ý | 1–3 câu tiếng Anh đơn giản, nghĩa tiếng Việt, căn cứ/thiếu căn cứ, thời điểm và đoạn hội thoại được dùng |

Điều khiển gợi ý: Ngắn hơn, Giải thích, Hỏi lại khách, Copy, Giữ câu đang đọc.

- Giữ câu đang đọc khóa card hiển thị, không dừng capture/backend.
- Gợi ý mới đi vào hàng đợi có nhãn "Có gợi ý mới"; người dùng chủ động chuyển.
- Khi đang đọc, không tự cuộn hoặc thay nội dung card.
- Có ô "Hỏi AI" cho yêu cầu thủ công và nút Tạo gợi ý từ đoạn đang chọn.
- Có chọn participant là "Tôi" khi tên người nói có sẵn; lưu choice theo session.
- Nếu chưa biết ai là người dùng, không tự khẳng định câu mới nhất là lời khách.
- Auto mode có thể tắt; manual mode vẫn dùng được.
- Nguồn mở trong drawer: trích đoạn, file/ticket, dòng/section, thời điểm snapshot. Code UI đọc nguồn, không mở URL tùy ý từ model.
- Phân biệt trạng thái đang xử lý, thiếu dữ liệu, lỗi AI và gợi ý đã sẵn sàng.

## UI-03 — Báo cáo sau họp

Route dashboard: /meetings/:meetingId/report.

Các phần:

1. Tổng quan ngắn.
2. Yêu cầu mới/thay đổi.
3. Quyết định đã xác nhận.
4. Action items.
5. Câu hỏi còn bỏ ngỏ.
6. Đề xuất của AI.
7. Cảnh báo chất lượng: mất capture, khoảng tạm dừng, thiếu nguồn hoặc hội thoại mơ hồ.

Action item gồm nội dung, owner hoặc "Chưa xác nhận", due hoặc "Chưa xác nhận", trạng thái, bằng chứng transcript.

- Mỗi ý dựa trên cuộc họp có thể mở bằng chứng theo segment ID.
- Đề xuất của AI có nhãn riêng; không biến nó thành quyết định của khách.
- Edit inline, lưu bản nháp, copy phần tiếng Việt hoặc tiếng Anh, xuất Markdown/JSON.
- Phiên bản report được lưu; tạo lại tạo phiên bản mới, giữ bản người dùng đã sửa.
- Không tự gửi báo cáo.
- Báo cáo từ phiên chưa đủ dữ liệu vẫn xuất được với cảnh báo rõ.

## UI-04 — Lịch sử

Route dashboard: /meetings.

Lọc project/ngày/từ khóa. Danh sách hiện tên, ngày, thời lượng quan sát, status, chất lượng capture, báo cáo đã có hay chưa.

Mở transcript/report; tìm trong transcript; xóa phiên và dữ liệu liên quan. Cuộc họp interrupted có thể tạo báo cáo phần đã thu được. Xóa project cần xử lý rõ dữ liệu cuộc họp, nguồn và index liên quan, bằng thao tác UI có xác nhận cụ thể.

## UI-05 — Cài đặt

Route dashboard: /settings.

- Backend URL local và pairing token của ứng dụng local.
- Provider/model, trạng thái API key, Test connection.
- Ngôn ngữ hiểu ý: Việt; câu trả lời: Anh; mức đơn giản A2–B1.
- Độ dài câu gợi ý, Auto/manual, glossary theo project.
- Lưu cuộc họp local bật/tắt; thời gian giữ mặc định 30 ngày, có thể đổi.
- Trạng thái semantic search, tải model local bằng thao tác chủ động; cache model được giữ.
- Số request, token usage nếu provider trả; cấu hình giá khi người dùng muốn ước tính chi phí.

API key đọc từ environment hoặc nhập vào bộ nhớ backend của lần chạy hiện tại. Không lưu key vào source code, browser storage hoặc log. Nếu muốn giữ key qua restart, bổ sung OS credential store; không lưu plaintext để làm nút Save có vẻ hoạt động.

UI Test connection phải thực sự gọi provider một request nhỏ; hiện rõ có thể phát sinh phí văn bản. Không coi mock response là kết nối thành công.

## 3. Trạng thái bắt buộc và chữ hiển thị

| Trạng thái | UI hiển thị | Action tiếp theo |
| --- | --- | --- |
| Chưa có project | “Tạo dự án hoặc chọn dự án để chuẩn bị ngữ cảnh” | Tạo/import; vẫn có thể capture bằng project rỗng đã chọn |
| Chưa có nguồn | “Chưa có dữ liệu dự án để đối chiếu” | Thêm nguồn hoặc dùng câu hỏi làm rõ |
| Đang index | Progress và last good version nếu có | Đợi; tìm theo version cũ với nhãn nếu tồn tại |
| Index lỗi | Lỗi + nguồn/version bị ảnh hưởng | Sửa input, reindex; không mất last good index |
| Chưa nhận caption | “Đang chờ lời nói hoặc kiểm tra phụ đề” | Xem hướng dẫn; không kết luận mất capture chỉ từ silence |
| Caption tắt có bằng chứng | “Hãy bật phụ đề trong Meet” | Người dùng bật CC |
| DOM chưa hỗ trợ | “Chưa nhận diện được vùng phụ đề” | Diagnostic metadata, hướng dẫn gửi thông tin adapter đã lọc |
| Backend mất kết nối | Đang reconnect + outbox/gap warning | Tự reconnect; vẫn chỉ claim phần đã quan sát |
| Đang pause | “Tạm dừng thu nội dung” + khoảng pause | Resume từ thời điểm hiện tại |
| Thiếu speaker | “Chưa rõ người nói” | Chọn Tôi khi có label, hoặc dùng manual |
| AI đang làm | Spinner nhỏ, request time; giữ card validated trước | Cancel/đợi; không ghi đè card pinned |
| AI missing/conflicting | Nhãn thiếu nguồn/mâu thuẫn và câu hỏi làm rõ | Mở excerpt, kiểm tra/hỏi lại |
| Caption đã sửa nghĩa | Card “Ngữ cảnh đã thay đổi” | Tạo lại hoặc kiểm tra snapshot đang đọc |
| Provider lỗi | Error code dễ hiểu + thử lại khi phù hợp | Sửa key/model/network; không tự retry auth lỗi |
| Report chưa reviewed | Badge Bản nháp | Mở bằng chứng, chỉnh, đánh dấu reviewed |
| Report edit conflict | Hai version được giữ để chọn/merge | Reload/merge; không silently overwrite |
| Memory mode | “Phiên chỉ giữ trong bộ nhớ lần chạy này” | Copy/export chủ động trước khi restart |

## 4. Luồng chính và chống thao tác nhầm

1. Mở dashboard → tạo/chọn project → preview/import nguồn → xem ready/error.
2. Mở Meet, bật caption tiếng Anh → extension action mở panel → chọn project → Start.
3. Project bị khóa theo session; header hiển thị project/tab. Mở tab Meet khác không tự gắn vào phiên cũ.
4. Caption hiển thị ngay theo observed text; gợi ý dựa trên stable snapshot, có timestamp và source.
5. Giữ câu đang đọc khóa card. Các action Ngắn hơn/Giải thích/Hỏi lại dùng snapshot của card này, kể cả transcript mới đã đến.
6. Pause ghi gap, Resume không thu bù nội dung pause. End flush/ACK hoặc hiển thị phần có thể thiếu.
7. Report mở thành draft; người dùng xem evidence, sửa, save version, copy/export.
8. Mở history tìm lại đúng phiên/project; xóa dữ liệu theo policy hiện rõ.

Đóng panel không kết thúc phiên. Kết thúc là action rõ ràng và idempotent. Xóa project/meeting dùng dialog ghi cụ thể dữ liệu sẽ xóa; action AI đề xuất không mở dialog cấp quyền thực thi vì MVP không thực thi.

## 5. Nội dung nguồn và báo cáo

Source drawer: title/type, snippet, path/ticket ID, line/section, indexed_at, origin_updated_at nếu có, snapshot/current version khác nhau. Khi nguồn bị xóa, nhãn xóa; không mở sang nguồn khác.

Action item UI có owner/due “Chưa xác nhận” khi null; raw relative date giữ trong evidence. Quyết định đã xác nhận và đề xuất AI có heading/badge riêng, kể cả khi nội dung giống nhau.

## 6. Kiểm chứng UI

Các check UX-01, UX-02, AI-06, CIT-01, REP-02, HIS-01 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md). Keyboard focus/label cơ bản phải dùng được; ưu tiên kiểm tra luồng và dữ liệu, không viết test chỉ lặp màu/nội dung CSS.

