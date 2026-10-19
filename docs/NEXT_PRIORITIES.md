# Chức năng và nghiệm thu tiếp theo

## Sau Phase 5

[Phase 5 candidate](PHASE5_REPORT.md) triển khai vận hành local. Ưu tiên đóng Meet thật/Windows độc lập/model-quality với budget được cấp, E5 load/shutdown và soak thực địa; mở rộng authority/coreference/multilingual và weighted matrix. CI/backup không thay các gate thực địa. Durable cost accounting và full-size corpus vẫn mở.

Các danh sách bên dưới là lịch sử ưu tiên trước khi làm từng phase.

## Sau Phase 4 — Phase 5

[Phase 4 PARTIAL và các giới hạn](PHASE4_REPORT.md). Ưu tiên CI/regression suite + fixtures, refactor ledger/report/API/DTO, setup/update/backup, upgrade/rollback/migration fault tests, total report budget/queue/concurrency, durable usage accounting, full RSS/corpus lớn và nghiệm thu Windows/Meet/recovery vận hành. Đánh giá model thật cần authorization + budget mới. Coreference/authority/multilingual và weighted options không tự được coi là đã triển khai từ ledger; không hạ guard để làm PASS.

## Sau Phase 3

[Kết quả Phase 3](PHASE3_REPORT.md): **PARTIAL**, hai mục tiêu request/Auto wait vẫn mở. Phase 4 ưu tiên corpus cuộc họp được phép dùng, chấm trigger/card hữu ích theo người, benchmark provider thật với budget mới và đóng Meet live gate; sau đó hiệu chỉnh indirect/multilingual trigger, paraphrase dedup, full RSS/index writer và cold retrieval. Không hạ ngưỡng hoặc bỏ câu hỏi/validator để hợp thức hóa PASS. Bảng phương án/trọng số vẫn chưa triển khai; memory đã có ở Phase 4 trong phạm vi công bố.

Bộ phân loại đã triển khai: [RESPONSE_ROUTING.md](RESPONSE_ROUTING.md). Giai đoạn 1 đã đóng các probe gốc và bất biến phiên trong phạm vi đã kiểm thử: [PHASE1_REPORT.md](PHASE1_REPORT.md). Các mục dưới là đề xuất tiếp theo, chưa triển khai chỉ vì được ghi trong tài liệu.

| Ưu tiên | Chức năng | Tiêu chí cần đạt |
| --- | --- | --- |
| P1 | Kiểm tra claim với đúng bằng chứng | Mở rộng guard giai đoạn 1 sang định tính, coreference, nhiều ngôn ngữ và corpus thực được phép dùng. Ba probe gốc đã bị chặn; fixture hiện 0 false accept/0 false reject nhưng không là accuracy thực tế. Đo thêm chặn nhầm và sai bị lọt ngoài grammar/alias hiện tại. |
| P1 | Bảng phương án và tính trọng số | 2–3 phương án có lợi ích/rủi ro/điều kiện/giả định. Tiêu chí và trọng số có nguồn hoặc người dùng xác nhận; kiểm tra ràng buộc bắt buộc trước xếp hạng. Backend tính tổng, không bịa confidence hay điểm dữ kiện thiếu; kiểm tra độ nhạy khi đổi trọng số. |
| P1 | Bộ nhớ quyết định/nhận việc/thay đổi | Theo dõi proposal/confirmed/rejected/superseded, đúng người/task, có turn gốc. Cập nhật khi caption sửa hoặc quyết định bị hủy; không phụ thuộc chỉ cửa sổ live ~3 phút. |
| P2 | Hỏi làm rõ theo dữ kiện thiếu và câu giữ lượt | Hỏi đúng ràng buộc quan trọng; câu giữ lượt không hứa việc/đưa đáp án chưa kiểm chứng. Người dùng chọn nói, app không tự phát ngôn. |
| P2 | Đo độ trễ tới giao diện theo từng luồng | Caption → stable → scheduled → provider → validated → rendered; tách warm/cold, correction/error, route và context size. Không bỏ guard để đạt tốc độ. |
| P2 | Nguồn cập nhật và báo cáo dài | Đồng bộ connector được chọn, freshness rõ; thử corpus thực, report nhiều giờ, gom mục trùng và giữ quyết định thay đổi. |

Nghiệm thu còn thiếu ngoài chức năng: Meet thật tối thiểu hai participant, đối chiếu capture, outage/reload/restart và Windows sạch. Chưa kết luận hệ thống sẵn sàng dùng chính thức trước khi đóng các gate này.

## Sau Phase 2

[Phase 2](PHASE2_REPORT.md) đã triển khai phần độc lập; ưu tiên đóng [live gate Meet hai participant](PHASE2_LIVE_RUNBOOK.md), đo ASR và lỗi ứng dụng riêng, hiệu chuẩn replacement/window/speaker trên DOM đã quan sát. Phase 3 tối ưu trigger, giảm Auto requests/revision burst và gợi ý lặp, theo cả ready/stale/error/cancelled. Không bỏ validator/capture fidelity để đổi lấy latency. Weighted matrix/decision memory/connector vẫn ngoài scope Phase 2.
