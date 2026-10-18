# Giới hạn và phần chờ kiểm chứng

Phase 3 **PARTIAL**: [báo cáo](PHASE3_REPORT.md). Logical request giảm 18,37% chưa đạt 20%; Auto đợi manual chậm 2,9 s chưa đạt 500 ms mọi câu ngắn. 39/39 chỉ là eligible đã attempted trên synthetic replay, không phải câu trả lời hữu ích. Card dedup rất hẹp, chưa xử lý paraphrase/topic; rules có thể miss indirect questions/tiếng Việt có dấu/cách nói mới. Focus tối đa 32 (vượt trả lỗi), retrieval tối đa 8 distinct inflight/1 worker, query LRU 128 và matrices 2 bộ không giới hạn byte RSS. Corpus 10k dùng vectors điều khiển; E5 thật chỉ 12 chunks. Keyword cold và E5 p95 có hồi quy được công khai. Narrow freshness chỉ cho cosmetic/new small talk khi revision log liên tục đủ; substantive changes vẫn stale. Không có paid provider call mới hoặc Meet thật được nghiệm thu.

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

[LATENCY_REPORT.md](LATENCY_REPORT.md) giữ số đo provider lịch sử trước routing/Phase 1–3: median 1,498 s trên 10 mẫu, 1,520 s trên 16 mẫu, max 3,399 s; chưa phải deadline cứng. Phase 3 thay debounce 2 s bằng trigger 150/800 ms, max batch 2 s khi rảnh; vẫn cộng thời gian adapter stable/retrieval/provider/render và chờ manual. Provider thật trên build mới/cold-first-suggestion/mạng/Meet thật chưa được xác minh.

## Bộ phân loại mới

[Response routing](RESPONSE_ROUTING.md) đã triển khai bằng quy tắc local Anh–Việt, chưa hiệu chuẩn trên corpus họp thật. Có thể phân loại sai câu gián tiếp/trích dẫn/cách nói mới. Preview không gọi AI nhưng vẫn có retrieval; available không chứng minh claim đúng. Deep mới đổi hướng dẫn trong schema gợi ý, chưa có bảng điểm trọng số. Mục tiêu 1–2/2–4/5–10 s theo luồng chưa được đo bằng provider thật trên build mới. Routing không thay semantic validation; ba probe gốc đã được giai đoạn 1 chặn trong [phạm vi được kiểm thử](PHASE1_REPORT.md). Chưa có provider benchmark sau thay đổi này. Các việc tiếp theo ở [NEXT_PRIORITIES.md](NEXT_PRIORITIES.md).

## Phase 2 — giới hạn còn lại

[Replay/recovery/telemetry](PHASE2_REPORT.md) đã có 228 backend / 56 frontend / 4 browser tests. Cắt WS bằng proxy 5/20 s trong Chromium thật đã phục hồi đúng fixture; đây chưa phải mạng/Meet live. Same-node text giống hệt không có mutation, short replacement, nhiều ứng viên giống nhau hoặc correction nằm ngoài window vẫn mơ hồ. Stable không phải final. Ngưỡng 160-token/1,5 s/3 s/overlap chỉ có bằng chứng synthetic; không phải đặc tính được Google bảo đảm.

Backend alive, content heartbeat, adapter status và caption arrival là các tín hiệu khác nhau. Selector tồn tại nhưng trỏ nhầm vùng hợp lệ không thể tự được chứng minh đúng; calibration phải được đối chiếu. Không có caption trong im lặng không chứng minh hỏng capture. Native Chrome side panel/Meet thật hai participant vẫn NOT TESTED. [Runbook](PHASE2_LIVE_RUNBOOK.md) và form đã sẵn. Không có benchmark model thật hoặc semantic mới trong Phase 2. Render notification gồm message/rAF, chưa phải pixel hoặc speech ground truth.
