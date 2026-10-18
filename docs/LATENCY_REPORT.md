# Tối ưu thời gian gợi ý hoàn chỉnh

**Kết quả thực đo: khoảng 1,5 giây trung vị; chưa bảo đảm mọi request ≤1,5 giây.** DeepSeek `deepseek-flash` thật, dữ liệu synthetic. Giữ bước parse JSON, đổi alias về ID gốc, kiểm tra evidence/negation/role/commitment rồi mới publish; không hiển thị token chưa kiểm tra.

| Phép đo | Trước | Sau |
| --- | --- | --- |
| Cùng 10 kịch bản mở rộng: median | 2.674 s | 1.498 s |
| 16 kịch bản cuối: median | — | 1.520 s |
| 16 kịch bản: min / p95 mẫu / max | — | 1.094 / 3.399 / 3.399 s |
| Request ≤1,5 s trong 16 mẫu | — | 6/16 |

Median trên bộ 10 mẫu tương ứng giảm 44.0%. So sánh lịch sử cùng fixture, không phải thí nghiệm mạng đồng thời. n nhỏ và có biến động provider/mạng; p95 mẫu không phải SLA.

## Đã thay đổi

- Dùng lại AsyncClient/connection pool, keepalive 60 s khi server cho phép; đóng pool khi backend shutdown. Mỗi request dùng credential hiện tại, không giữ Authorization trong client mặc định.
- Live dùng hướng dẫn ngắn và một câu trả lời dễ nói; action explain/ask vẫn có thể giải thích theo yêu cầu. Report vẫn giữ pipeline/schema đầy đủ.
- Chỉ bỏ metadata vận chuyển/lưu trữ khỏi prompt live; giữ nguyên lời thoại, memory, glossary, nội dung nguồn và cờ stale. Snapshot đầy đủ/citation metadata vẫn lưu như trước.
- Dùng ID C1/T1 trong request thay cho UUID dài. Backend đổi về đúng ID gốc; alias lạ bị chặn và không lẫn mapping giữa các request.
- Ưu tiên turn mới nhất; sửa lỗi theo đúng loại lỗi, tối đa một lượt. Không tăng số lần retry lỗi auth/timeout/JSON sai để đạt số đo đẹp.

## Phạm vi thời gian

Đo thời gian tạo và kiểm tra gợi ý tại backend, gồm lượt sửa nếu có. Connection test làm ấm client trước corpus; request đầu lạnh chưa được chứng minh ở 1,5 giây. Không dùng cache câu trả lời của ứng dụng để tạo số đo, nhưng prefix cache của provider vẫn hoạt động.

Auto vẫn giữ stable khoảng 1 s và debounce 2 s theo cấu hình hiện tại. Vì thế 1,5 s ở đây không phải từ lúc người khác bắt đầu nói hoặc từ khi phụ đề đang đổi tới UI. Meet thật, cold start, corpus lớn và mạng chậm vẫn cần đo riêng.

## Giữ lại các lượt thử chưa đạt

| Bước | Số case quan sát | Gợi ý được chấp nhận | Lỗi | Median của gợi ý được chấp nhận |
| --- | --- | --- | --- | --- |
| Shared HTTP client | 10 | 10 | 0 | 1.671 s |
| Compact live prompt | 10 | 10 | 0 | 1.564 s |
| Short IDs (incomplete harness run) | 9 | 9 | 0 | 1.590 s |
| Short outputs, before targeted correction | 16 | 15 | 1 | 1.293 s |
| Final verified profile | 16 | 16 | 0 | 1.520 s |

Lượt short-ID đầu bị lỗi ghi evidence trên Windows ở case thứ 9; file cuối vẫn giữ chín kết quả và credential đã được xóa. Harness chuyển sang ghi file tạm + replace có lock/retry. Lượt trước final có một kết quả bị role guard chặn; không tính nó thành thành công và không bỏ guard. Lượt cuối có đủ 16/16 gợi ý được chấp nhận.

## Kết quả từng case cuối

| Case | Check | Hoàn chỉnh |
| --- | --- | --- |
| numbers-and-units | PASS | 1.525 s |
| ambiguous-we-owner | PASS | 1.767 s |
| confirmed-relative-date | PASS | 1.457 s |
| deadline-replaced | PASS | 1.515 s |
| rejected-production-proposal | PASS | 1.575 s |
| same-ticket-project-isolation | PASS | 1.396 s |
| injected-source-document | PASS | 1.481 s |
| confirmed-owner-transfer | PASS | 1.094 s |
| schema-is-not-deployment | PASS | 2.093 s |
| long-report-start-middle-tail | PASS | 1.467 s |
| regression-negative-deployment | PASS | 1.467 s |
| regression-tentative-deadline | PASS | 1.586 s |
| regression-missing-status | PASS | 1.509 s |
| regression-conflicting-api17 | PASS | 1.748 s |
| regression-untrusted-instructions | PASS | 2.273 s |
| regression-multi-participant-review | PASS | 3.399 s |

[JSON có guards/checks/source hashes](evidence/speed-review.json) · [Evidence lượt cuối](evidence/speed-repeat.json) · [Fixture 16 mẫu](../fixtures/speed-scenarios.json)

Các test mới kiểm tra reuse/fresh credential/close pool, hủy stream, round-trip alias/scope, giữ evidence khi rút prompt và không retry thêm timeout/auth/bad JSON. Semantic guard vẫn chỉ bao phủ một số mẫu ngôn ngữ; cần đối chiếu nội dung quan trọng trước khi dùng.

## Phạm vi build sau khi thêm routing

Các số đo trong báo cáo này là benchmark trước khi thêm [response routing](RESPONSE_ROUTING.md). Build mới có prompt theo luồng và preview/retrieval bổ sung; chưa chạy lại provider benchmark cho fast/explain/deep/clarify. Không suy số đo cũ thành SLA hoặc thời gian của các luồng mới.
