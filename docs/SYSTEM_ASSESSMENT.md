# Đánh giá hệ thống hiện tại

## Trạng thái Phase 3

[Phase 3](PHASE3_REPORT.md) **PARTIAL theo mục tiêu đặt trước**; 276 backend / 58 frontend / 5 browser pass. Trigger/scheduler/manual/context/retrieval và accounting đã cải thiện trên replay: eligible attempted 37/39 → 39/39, false trigger 7 → 0, logical 49 → 40. Giảm 18,37% chưa đạt 20%; Auto sau manual chậm 2,9 s chưa đạt 500 ms. Không suy ra chất lượng model thật từ controlled ready cards. Guard Phase 1 và capture Phase 2 vẫn regression pass; live Meet/provider benchmark mới NOT TESTED. Bảng đánh giá lịch sử dưới đây không thay kết luận hiện tại.

## Trạng thái sau giai đoạn 1

Đã đóng bất biến phiên và ba probe sai nghĩa gốc **trong phạm vi guard có cấu trúc/alias đã kiểm thử**. Kết quả A–E, 219 backend tests và 82 fixture positive/negative ở [PHASE1_REPORT.md](PHASE1_REPORT.md); [evidence mới](evidence/phase1/semantic-review.json) giữ riêng khỏi các probe trước sửa. Không coi đây là xác minh ngữ nghĩa tổng quát hoặc MVP VERIFIED.

Source hiện kiểm tra số theo thuộc tính/đơn vị/phủ định/điều kiện, task theo đúng hành động/đối tượng/người nhận, và confirmation theo đúng mệnh đề/môi trường; áp dụng trong pipeline và repair, cả summary/item và hai trường ngôn ngữ. Những phát hiện phía dưới là lịch sử trước sửa, không phải kết luận hiện tại. Meet thật và các gate vận hành vẫn còn mở.

## Đánh giá trước giai đoạn 1 — lịch sử

Kết luận: phù hợp để bắt đầu thử nghiệm có giám sát; chưa đủ bằng chứng để nghiệm thu sử dụng thực tế. Phần lõi đã triển khai và có kiểm tra, nhưng đầu vào Meet thật chưa được xác minh và validator chưa xác minh toàn bộ quan hệ giữa lời khẳng định và bằng chứng.

## Kiểm tra trong lượt đánh giá này

- Backend: 48/48 pass, một cảnh báo deprecation của dependency test.
- Extension unit: 13/13 pass; TypeScript và OpenAPI/TypeScript contract checks pass.
- Không gọi provider trả phí trong lượt này. Ba browser E2E pass là bằng chứng của lượt trước, không chạy lại trong lượt đánh giá này.
- Đọc code capture/storage/service/provider, giới hạn triển khai và báo cáo nghiệm thu/latency.
- Chạy ba probe trực tiếp với validator bằng đầu ra model cố tình sai. Cả ba đều được validator chấp nhận. Đây là giới hạn của validator, không phải phép đo tần suất model trả lời sai.

## Phát hiện cần ưu tiên

| Ưu tiên | Phát hiện | Bằng chứng và tác động |
| --- | --- | --- |
| P1 | Chưa nghiệm thu caption trên Google Meet thật | Adapter dùng calibration và heuristic; các bài capture/recovery hiện dùng DOM synthetic. Chưa biết tỷ lệ thiếu/lặp/nhầm speaker trong cuộc họp thực tế. |
| P1 | Citation đúng ID vẫn có thể đi kèm nội dung sai | Probe nguồn ghi timeout 15 giây nhưng finding/reply ghi 90 giây vẫn qua validation. Cần kiểm tra quan hệ giữa claim và excerpt, ưu tiên số, phủ định, trạng thái và scope. |
| P1 | Kiểm tra nhận việc chưa gắn với đúng task | Minh nhận review CSV nhưng reply hứa viết lại authentication vẫn được chấp nhận, vì guard hiện nhận ra đã có một lời nhận việc. |
| P1 | Xác nhận quyết định chưa gắn với đúng mệnh đề | Transcript xác nhận staging, production còn chờ duyệt; report ghi production được duyệt vẫn qua validator. Summary cũng chưa được kiểm tra nghĩa đầy đủ. |
| P2 | Mục tiêu 1,5 giây chưa phải thời gian đầu cuối | Benchmark cuối: median backend 1,520 giây, max 3,399 giây, 6/16 request ≤1,5 giây; client đã làm ấm. Auto còn thời gian stable khoảng 1 giây và debounce 2 giây. Chưa đo từ speech/caption tới UI trên Meet thật. |
| P2 | Hội thoại dài và tích hợp còn giới hạn | Live chỉ dùng cửa sổ gần đây và memory được chọn; nguồn là snapshot repo/text/schema/CSV/JSON. Chưa có connector đồng bộ sống, PDF/DOCX, thử họp hàng giờ hoặc corpus dự án lớn. |
| P2 | Vận hành mới ở mức một máy local | Chưa nghiệm thu máy Windows sạch độc lập, outage trong Meet thật và dùng dài hạn. Chưa có installer/autostart/vault; thiết kế hiện phục vụ một người dùng, một meeting active. |

Các P1 về validator đã được tái hiện cục bộ, chưa sửa trong lượt đánh giá này. Không cộng chúng thành lỗi model thực tế hay tỷ lệ lỗi tổng quát.

## Phần đã có giá trị

Storage có revision/ACK, local/RAM, khoảng thiếu, retention và cascade delete. Request giữ snapshot gốc, nguồn cách ly project, citation tra cứu được; scheduler xử lý stale/cancel/latest queued. Báo cáo có version/edit/export và không lấy gợi ý AI làm lời nói của người tham gia. Provider đã được thử thật trên fixture synthetic, không tự chuyển sang demo khi lỗi. API local có token, kiểm tra Host/Origin và credential nhập qua UI chỉ giữ trong RAM backend. Đây là các kiểm soát đã có mã/test, không phải chứng nhận an toàn toàn diện.

## Trình tự nên làm tiếp

1. Biến ba probe sai nghĩa thành regression tests phải bị chặn; bổ sung kiểm tra claim theo đúng task/mệnh đề và đối chiếu số liệu. Đo lại cả false positive trên các mẫu đúng, thay vì chỉ siết regex cho ba câu này.
2. Thử Meet thật tối thiểu hai participant, đối chiếu transcript với kịch bản gốc; thử partial, phủ định, speaker, pause/resume, reload và mất mạng. Ghi độ trễ đầu cuối cùng số đoạn thiếu/lặp.
3. Chạy cuộc họp dài và corpus dự án thực tế, đo nhiều mẫu hơn cho latency, chất lượng và usage; kiểm tra setup trên Windows sạch trước khi nghiệm thu.

## Bằng chứng

- [Ba probe validator, đầy đủ input/output](evidence/system-assessment-probes.json)
- [Giới hạn triển khai](LIMITATIONS.md)
- [Báo cáo nghiệm thu](ACCEPTANCE_REPORT.md)
- [Số đo latency](LATENCY_REPORT.md)

## Cập nhật sau đánh giá

Đã bổ sung [bộ phân loại local và gate xác minh](RESPONSE_ROUTING.md). Đây là bước định tuyến trước sinh câu trả lời, chưa phải kiểm tra ngữ nghĩa đầy đủ và không đóng ba phát hiện validator nêu trên. Các số lượng test trong phần đánh giá ban đầu là lịch sử; xem ACCEPTANCE_REPORT và backend-tests.xml cho lượt mới. [Ưu tiên tiếp theo](NEXT_PRIORITIES.md).

## Trạng thái Phase 2 hiện tại

[Capture/recovery/latency A–G](PHASE2_REPORT.md): 8 lỗi replay trước sửa đã đóng trong corpus synthetic; 228 backend / 56 frontend / 4 browser pass. Outage 5/20 s, mất ACK, stale revision, pause/reload/worker/backend recovery được kiểm tra theo scope của từng tầng. Không có chứng nhận capture mọi DOM hoặc semantic entailment tổng quát. A/B/F PARTIAL, C/D/E PASS trong automated scope, G Meet thật NOT TESTED. Số latency DeepSeek cũ không được tái chứng nhận; [live runbook](PHASE2_LIVE_RUNBOOK.md) là bước tiếp.
