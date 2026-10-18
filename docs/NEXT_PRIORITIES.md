# Chức năng nên bổ sung sau bộ phân loại

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
