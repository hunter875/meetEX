# Giới hạn và phần chờ kiểm chứng

Trạng thái: **implementation chạy local, chờ nghiệm thu live**. Không gọi đây là MVP VERIFIED. P2 connector/DB sống/PDF-DOCX/installer chưa triển khai và không có nút giả đã kết nối.

## Capture

Chưa có meeting thật hai participant để xác nhận DOM/profile. Lần đầu cần calibration chủ động; khi Google đổi cấu trúc cần chọn lại. Selector có thể phụ thuộc vị trí element. Speaker chỉ là label, không xác minh danh tính. Caption Google nhận sai vẫn được giữ nguyên; AI không sửa transcript gốc.

Đoạn đã render trước Start/Resume bị bỏ qua, kể cả phần đầu turn đang tiếp diễn. Turn boundary và stable là heuristic; câu y hệt từ cùng speaker, node recycle quá nhanh hoặc câu sửa hoàn toàn có thể mơ hồ. Không đủ tín hiệu thì unknown, không suy im lặng thành captions_off. Calibration chưa tự nhận diện toggle/meeting-left đa ngôn ngữ.

Chromium đã nạp manifest MV3, chạy content script, rebind/restart worker, đóng panel document và thử 320 px với DOM synthetic. Chưa kiểm tra user gesture trên toolbar/native side panel trong Chrome cá nhân; chưa thử network outage 20 giây trong một meeting thật.

## AI và bằng chứng

Giai đoạn 1 đã chặn ba probe gốc và thêm đối chiếu claim có giới hạn: [phạm vi, test và hạn chế](PHASE1_REPORT.md). 219 backend tests và 82 fixture không chứng minh mọi claim đúng. Nguồn số liệu hỗ trợ các nhãn/đơn vị được khai báo; task/confirmation dùng alias và mệnh đề, không có entailment/coreference tổng quát. Unknown confirmed/supported trong phạm vi guard sẽ bị chặn hoặc yêu cầu partial/hỏi lại; câu hỏi dẫn dắt, phủ định lồng, named entity/cách nói mới và bản dịch ngoài alias vẫn có thể lọt hoặc bị chặn nhầm. User edit và lịch sử cũ không được tự sửa hay tái chứng nhận. Cache có phiên bản validation policy để không tái dùng kết quả cũ cho yêu cầu mới.


Đã dùng key do người dùng cung cấp qua RAM để chạy `deepseek-flash` thật: [6 tình huống ban đầu](LIVE_PROVIDER_REPORT.md) và [10 tình huống mở rộng](EXTENDED_LIVE_REPORT.md). Key được xóa khỏi backend sau mỗi run. Đã thử transcript synthetic 43 turns/gần 20 nghìn ký tự qua hai map thật và giữ yêu cầu đầu/giữa/cuối. Chưa thử buổi họp hàng giờ, corpus dự án thật hoặc đủ nhiều prompt injection để suy accuracy/an toàn tổng quát. Các tests mặc định không gọi API trả phí; script live phải chạy chủ động và nhập key. Demo vẫn là controlled output có nhãn.

Validation chặn schema, ID ngoài scope, revision sai, claim deploy đối nghịch một số mẫu phủ định, owner/date thiếu bằng chứng và một số confirmation mơ hồ. Những guard này có thể bảo thủ và **không chứng minh mọi claim đúng nghĩa**. ID nguồn hợp lệ chỉ chứng minh nguồn tồn tại. Cần mở excerpt/transcript và xem lại trước khi nói/gửi báo cáo.

Live context dùng cửa sổ gần đây cùng nguồn chọn lọc, glossary và tối đa 8 đoạn memory do người dùng chọn rõ là đã xác nhận. Budget hiện giới hạn ký tự JSON (18.000), không phải tokenizer DeepSeek chính xác. Memory dài vượt budget có count bị bỏ, không cắt ngầm một câu thành fact. Caption sửa memory thì bỏ xác nhận và đánh dấu card liên quan stale.

Streaming được buffer rồi validate JSON; không hiển thị token preview. Suggestion/report vi phạm kiểm tra evidence/ngữ nghĩa có tối đa một lượt yêu cầu model sửa từ cùng transcript/sources, có thêm chi phí/latency. Vẫn sai thì báo lỗi, không xuất bản bản nháp bị chặn. JSON sai schema vẫn lỗi ngay. Guard không chứng minh mọi claim đúng; kiểm tra coverage hiện nhận một số cam kết tiếng Anh “I will”, không phải bộ phân tích mọi ngôn ngữ. Report dài map theo turn/overlap và merge/dedup theo text/evidence; summary các phần được ghép, chưa phải một lượt tổng hợp ngữ nghĩa cuối riêng.

Backend cấp ID riêng cho các mục sau merge, tránh ID model lặp giữa các map. Các câu hỏi tương tự nhưng diễn đạt khác vẫn có thể lặp; việc phân loại requirement/open question có thể cần chỉnh tay. Kiểm tra nhận việc dùng một số mẫu câu của đúng speaker; không chứng minh mọi lời hứa đều khớp chính xác một task đã nhận.

## Dữ liệu và vận hành

Repo/text/ticket/schema/export đều là snapshot. Import JSON UTF-8 từ browser file picker/paste hoặc đường dẫn local; không có multipart/archive/connector sống. Lần sync đọc lại file để hash; file không đổi không embed lại. Publish generation atomically; lỗi giữ generation trước có stale warning. Add/reindex API chờ job kết thúc trong khi UI hiện busy; job/status vẫn được lưu để kiểm tra.

FTS5 fallback tiếng Việt → nguồn tiếng Anh có giới hạn khi glossary không khớp và E5 chưa nạp. E5 CPU đã được chạy với revision pin trên corpus synthetic 12 nguồn; kết quả top-5 10/10 không phải accuracy tổng quát. Chưa benchmark repo lớn/generation hàng trăm MiB; SQLite chỉ có một writer, index lớn có thể làm ACK chậm hơn.

Optional semantic lock đã thử trên Python 3.13.4 / Windows x64; runtime Python khác chưa được xác minh. Model download cần mạng và dung lượng cache. Windows không bật symlink vẫn tải được bằng bản sao, có thể dùng thêm đĩa. Sau restart cần nạp model lại bằng Settings; cache giữ và FTS5 tiếp tục sẵn sàng.

Retention mặc định 30 ngày, theo UTC timestamps và ngày hiển thị theo timezone phiên. Backend cleanup định kỳ mỗi 15 giây và lúc startup. Phiên RAM không ghi caption/request/report vào SQLite/file. Browser RAM cache có thể tồn tại đến khi kết nối lại backend; reconnect/deletion event bỏ cache phiên không còn. Chrome đóng/restart mất outbox RAM; có thể thiếu đoạn cuối chưa ACK.

Source deletion bỏ current index và đánh dấu historical citation missing; trích đoạn đã nằm trong báo cáo/gợi ý giữ tới khi xóa meeting/project. Meeting deletion cascade dữ liệu backend và gửi event xóa cache extension; nếu extension offline cache RAM được đối chiếu ở reconnect.

Đã chạy PowerShell setup/build/start/health/Ctrl+C trên Windows hiện tại; chưa có máy Windows sạch độc lập. Backend chỉ một người dùng/worker/meeting active, bind 127.0.0.1:8765. Không có auto-start/installer/OS credential vault. Key nhập qua UI chỉ RAM backend; muốn giữ key qua restart dùng environment được quản lý riêng.

Các số đo capture ít mẫu và chỉ DOM synthetic. Đã ghi timing/usage thật trên nhóm 16 provider attempts (suggestion/report/connection/correction gộp): median khoảng 2,90 giây; đây không phải SLA hay thời gian riêng của gợi ý. Không có hóa đơn hay benchmark dài hạn chứng minh mục tiêu 2–5 giây. Usage thiếu giữ unknown; bảng giá do người dùng cấu hình có ngày, estimate không phải billing.

Sau tối ưu, [LATENCY_REPORT.md](LATENCY_REPORT.md) tách riêng gợi ý: median 1,498 s trên 10 mẫu tương ứng và 1,520 s trên 16 mẫu cuối; 6/16 request ≤1,5 s, max 3,399 s. Chưa đảm bảo deadline cứng 1,5 s. Đo sau connection test làm ấm client; cold-first-suggestion, mạng chậm và Meet thật chưa được xác minh. Auto vẫn cộng khoảng 1 s ổn định phụ đề + 2 s debounce. Các lời giải thích live ngắn hơn; muốn giải thích chi tiết dùng action explain/ask, có thể chậm hơn.

## Bộ phân loại mới

[Response routing](RESPONSE_ROUTING.md) đã triển khai bằng quy tắc local Anh–Việt, chưa hiệu chuẩn trên corpus họp thật. Có thể phân loại sai câu gián tiếp/trích dẫn/cách nói mới. Preview không gọi AI nhưng vẫn có retrieval; available không chứng minh claim đúng. Deep mới đổi hướng dẫn trong schema gợi ý, chưa có bảng điểm trọng số. Mục tiêu 1–2/2–4/5–10 s theo luồng chưa được đo bằng provider thật trên build mới. Routing không thay semantic validation; ba probe gốc đã được giai đoạn 1 chặn trong [phạm vi được kiểm thử](PHASE1_REPORT.md). Chưa có provider benchmark sau thay đổi này. Các việc tiếp theo ở [NEXT_PRIORITIES.md](NEXT_PRIORITIES.md).
