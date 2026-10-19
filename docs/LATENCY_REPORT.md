# Tối ưu thời gian gợi ý hoàn chỉnh

## Phase 4 — overhead có evidence

[Paired report/memory evaluation](PHASE4_REPORT.md): 321 synthetic turns/16 maps, Provider SSE adapter intercepted 5 ms controlled delay. Report 645,88 → 703,77 ms; HTTP attempts vẫn 16, retry/repair 0, usage unknown 16. Full caption apply median/p95 0,129/0,247 → 0,821/0,920 ms; memory update median/p95 0,632/0,686 ms. Đây là RAM fixture/samples nhỏ, không SLA/disk/Meet/model latency.

Replay Phase 3 vẫn 40 logical/42 HTTP và 39/39 eligible attempted; wire user JSON 27.197 → 28.931 ký tự (+6,38%) do memory. Không quy thành token/cost thật. No extraction/synthesis model call mới; chưa benchmark provider trả phí sau Phase 4.

**Số đo provider phía dưới là lịch sử trước routing và Phase 1–3**, không đại diện build hiện tại. Benchmark provider thật mới: NOT TESTED. [Phase 3](PHASE3_REPORT.md) đo scheduler controlled và retrieval riêng, không có paid calls mới. Idle short-question wait 2.000 → 150 ms clock ảo; Auto sau manual chậm vẫn 2.900 ms. Đây không phải speech-to-UI hoặc model latency.

Kết quả lịch sử: khoảng 1,5 giây trung vị; chưa bảo đảm mọi request ≤1,5 giây. DeepSeek `deepseek-flash` thật, dữ liệu synthetic. Giữ bước parse JSON, đổi alias về ID gốc, kiểm tra evidence/negation/role/commitment rồi mới publish; không hiển thị token chưa kiểm tra.

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

Trong benchmark lịch sử Auto dùng stable khoảng 1 s và debounce 2 s. Phase 3 thay debounce bằng trigger 150/800 ms, max batch 2 s khi rảnh; adapter stable vẫn là heuristic riêng. Vì thế 1,5 s ở đây không phải từ lời nói tới UI. Meet thật, cold start, corpus thật lớn và mạng chậm vẫn cần đo riêng.

## Số đo Phase 3 riêng

31 scenario synthetic, 39 eligible; logical 49 → 40, HTTP attempts 51 → 42, retry/repair đều được tính. Wire user JSON 32.384 → 27.197 ký tự; không quy đổi thành token thật hoặc tiền. Hybrid controlled-vector 10k cold 8.369,53 → 2.490,17 ms; warm median 9.598,47 → 1,00 ms sau 9/12 cache hits. Uncached mới median 252,00 ms (n=3), không phải 1 ms. Keyword cold 10k xấu hơn 168,32 → 218,30 ms. E5 thật corpus nhỏ median 45,75 → 36,11 ms nhưng p95 52,95 → 68,97 ms. [Bảng đầy đủ, RAM/tick/ACK và lệnh tái tạo](PHASE3_REPORT.md#context-retrieval-và-trade-off). Không dùng p95 mẫu nhỏ làm SLA.

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

## Phase 2 — metric mới, provider thật chưa chạy lại

Bảng DeepSeek phía trên là lịch sử. Phase 2 dùng Provider adapter + SSE MockTransport trong test, **0 paid calls**; không dùng số đo bên dưới để tuyên bố model đạt 1,5 s. [Định nghĩa clock/correlation](PHASE2_REPORT.md), [raw review theo nhóm](evidence/phase2/review.json). Error/cancelled được giữ trong request denominator; panel đóng/pinned hoặc revision không match có missing_render_n. Cold/warm chỉ việc tái dùng HTTP client; semantic mới và speech→rendered NOT TESTED.

Mọi số sau là **milliseconds, synthetic**, keyword retrieval, Chromium 141/Windows 11. Provider intercepted không có TLS/model/network thật; n rất nhỏ, p95 nearest-rank thường bằng max. Manual gồm thời gian đợi trước khi trigger, Auto có heuristic stable + debounce hiện hành.

| Phép đo | n | Median ms | p95 ms | Max ms |
| --- | ---: | ---: | ---: | ---: |
| observed_to_ack_ms | 15 | 1044.30 | 30879.30 | 30879.30 |
| stable_to_schedule_received_ms | 6 | 1280.45 | 2022.00 | 2022.00 |
| observed_to_rendered_notification_ms | 4 | 2211.60 | 3205.10 | 3205.10 |
| stable_to_rendered_notification_ms | 4 | 1149.70 | 2107.00 | 2107.00 |

ACK gồm cả outage 5/20 s và stable revisions (chờ heuristic); max 30,88 s trong bài mất mạng 20 s, có thêm backoff reconnect. Không gọi đây là latency bình thường hoặc speech→rendered.

| Render group | n | Observed→render median / p95 / max ms | Stable→render median / p95 / max ms |
| --- | ---: | --- | --- |
| manual/ready | 3 | 2100.30 / 2322.90 / 2322.90 | 1038.40 / 1261.00 / 1261.00 |
| auto/ready | 1 | 3205.10 / 3205.10 / 3205.10 | 2107.00 / 2107.00 / 2107.00 |

Tất cả 8 request của phiên Phase 2: 5 ready, 1 stale, 1 error, 1 cancelled. Có 4 rendered notification tương quan; 4 request không có render gồm 1 ready, stale, error và cancelled. Không biến những mẫu thiếu này thành zero hoặc loại khỏi denominator.

| Request group (trigger / client / retrieval / code branch / outcome) | Request n | Provider ms: n, median / p95 / max | Validation ms: n, median / p95 / max | Không có render |
| --- | ---: | --- | --- | ---: |
| manual/cold/keyword/real/ready | 1 | 1, 10.276 / 10.276 / 10.276 | 1, 1.013 / 1.013 / 1.013 | 0 |
| manual/warm/keyword/real/ready | 3 | 3, 4.051 / 4.061 / 4.061 | 3, 1.138 / 1.303 / 1.303 | 1 |
| manual/warm/keyword/real/error | 1 | 1, 3.319 / 3.319 / 3.319 | 0, — | 1 |
| manual/warm/keyword/real/stale | 1 | 1, 809.360 / 809.360 / 809.360 | 1, 0.666 / 0.666 / 0.666 | 1 |
| manual/warm/keyword/real/cancelled | 1 | 1, 42.285 / 42.285 / 42.285 | 0, — | 1 |
| auto/warm/keyword/real/ready | 1 | 1, 3.593 / 3.593 / 3.593 | 1, 2.820 / 2.820 / 2.820 | 0 |

`real` trong group là nhánh Provider class của app; môi trường này **MockTransport**. Request error có provider timing nhưng không validation/card; cancelled đo đến cancellation, không phải thời gian hoàn tất model. Request stale provider được cố ý delay 0,8 s. Stable→scheduled backend có raw n/median/p95/max từng nhóm trong review; Auto warm n=1 là 2008,82 ms, gồm debounce 2 s. Provider thật, semantic mới và speech ground truth: **NOT TESTED**.
