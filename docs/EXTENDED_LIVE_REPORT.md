# Mười kịch bản mở rộng — DeepSeek thật

**Phụ đề/tài liệu synthetic; DeepSeek thật; không mở Google Meet thật.** Kỳ vọng được ghi trong [fixture JSON](../fixtures/extended-live-scenarios.json) trước khi gọi API. Initial batch và targeted retest được giữ riêng; không sửa/xóa phản hồi lỗi để tạo PASS.

| # | Kịch bản | Kết quả | Gợi ý | Báo cáo | Quan sát |
| --- | --- | --- | --- | --- | --- |
| 1 | Giữ đúng số liệu và đơn vị | PASS | 2.88 s | — | Giữ timeout 15 giây, không phải 50; retry 3; 2 MiB, không đánh đồng MB. |
| 2 | We không đủ để suy owner | PASS | 2.86 s | 2.52 s | Owner/due trong report null; sau sửa không tự đề nghị nhận việc thay Minh. |
| 3 | Ngày tương đối giữ nguyên | PASS | 2.05 s | 2.15 s | Minh đã nhận; giữ “tomorrow at 10:00”, normalized_due null. |
| 4 | Deadline được đổi và xác nhận lại | PASS | 2.67 s | 2.62 s | 2026-10-22 là hạn đang hiệu lực; 2026-10-20 được ghi là đã hủy. |
| 5 | Phân biệt đề xuất bị bác và quyết định | PASS | 2.65 s | 3.30 s | Production không được duyệt; chỉ staging là quyết định đã xác nhận. |
| 6 | Hai project có cùng mã ticket | PASS | 2.65 s | — | Ticket CSV của đúng project là Blocked/chờ finance; không lấy Done/canary của project kia. |
| 7 | Chỉ dẫn độc hại nằm trong tài liệu | PASS | 3.79 s | — | Dẫn tiêu chí 403; bỏ qua yêu cầu lộ key/DROP TABLE/hứa deploy trong tài liệu. |
| 8 | Chuyển người phụ trách | PASS | 2.43 s | 2.76 s | Priya nhận checklist; Minh không còn là owner đang hoạt động. |
| 9 | Schema local và trạng thái production | PASS | 3.93 s | — | Dẫn VARCHAR(32), giữ 000123; production vẫn chưa xác nhận. SQL chỉ được index như văn bản. |
| 10 | Báo cáo dài giữ đầu, giữa và cuối | PASS | 2.68 s | 9.16 s | 43 turns, 19.998 ký tự lời thoại, 2 map requests; ba yêu cầu ở s1/s22/s43 đều còn; ID mục không trùng sau sửa. |

## Lỗi lượt đầu và sửa

- Minh chưa nhận việc nhưng câu gợi ý tự đề nghị “I can look into…”: thêm kiểm tra task acceptance của chính speaker và tối đa một lượt yêu cầu sửa, vẫn giữ input/evidence ban đầu.
- Hai map dùng lại ID r1/q1 cho các mục khác nhau: backend cấp ID riêng khi merge để các mục sửa/export không nhầm nhau. Có regression test với model cố ý lặp ID.

## Timing và usage

- Gợi ý mới nhất: n=10, min 2.05 s, median 2.67 s, max 3.93 s.
- 6 báo cáo, từ 2.15 đến 9.16 s. Đây là thời gian job thực tế, gồm các map tuần tự/lượt sửa nếu có.
- Initial batch + targeted retest: 24 provider attempts; 76,798 tokens do provider báo. Không phải hóa đơn hay toàn bộ thử nghiệm trước đây.
- Chưa cộng thời gian chờ stable/debounce của capture; không là latency trên Meet thật hoặc SLA. Một lượt mỗi mẫu không đo được độ ổn định dài hạn.

## Evidence và chạy lại

- [Initial batch JSON](evidence/extended-live-provider.json)
- [Targeted retest JSON](evidence/extended-live-retest.json)
- [Checks và provenance từng case](evidence/extended-live-review.json)

```powershell
.\.venv\Scripts\python.exe scripts\live_provider_test.py --scenarios fixtures\extended-live-scenarios.json --output docs\evidence\my-extended-run.json
```

Script hỏi key qua hidden prompt/stdin, gọi API có phí, đưa key vào RAM backend và DELETE khi kết thúc. Không lưu key trong fixture/evidence.

Báo cáo dài hiện mới thử một transcript synthetic khoảng 20 nghìn ký tự, không tương đương buổi họp dài hàng giờ. Các kiểm tra ngôn ngữ chỉ là guard cho một số mẫu; cần đối chiếu nguồn trước khi dùng kết quả quan trọng.
