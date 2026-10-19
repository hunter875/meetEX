# Phân loại mức xử lý câu hỏi

## Phase 4 — memory trong routing/live

Snapshot live có structured ledger còn hiệu lực/cần làm rõ và raw evidence revision, cùng source retrieval riêng. Memory revision vào hash/freshness; old card action giữ snapshot với cảnh báo stale. Không lấy user note/AI proposal làm participant acceptance. Guard bổ sung chặn current claims trái cancelled/disputed và buộc quy nguồn user edit; mọi route vẫn qua guard Phase 1. [Budget/cadence/API/phạm vi](MEETING_MEMORY.md). Bare Yes/authority/coreference chưa được tự xác nhận, không trả confidence chưa hiệu chuẩn.

Trạng thái: đã triển khai quy tắc local `rules-v1`, API xem trước, scheduler/provider và giao diện. Chưa nghiệm thu Meet thật hoặc đo chất lượng đầu ra/độ trễ bằng provider thật sau thay đổi này. Không thêm lượt gọi model để phân loại.

## Luồng xử lý

| Luồng | Điều kiện | Hành vi |
| --- | --- | --- |
| fast | Chưa thấy yêu cầu phân tích nhiều hướng; dữ kiện có nguồn hiện hành | Ưu tiên câu trả lời ngắn, giữ kiểm tra evidence hiện có |
| explain | Hỏi lý do/cách hoạt động hoặc action Giải thích | Giải thích lý do chính và một giới hạn |
| deep | So sánh, phương án, đánh đổi hoặc chọn Phân tích sâu | Prompt yêu cầu 2–3 hướng, lợi ích/đánh đổi/điều kiện, đề xuất có điều kiện; chưa có bảng điểm trọng số |
| clarify | Yêu cầu duyệt/cam kết/nhận việc, xóa dữ liệu, mâu thuẫn rõ; hỏi dữ kiện nhưng nguồn thiếu/cũ | Hỏi lại/xác minh trước khi chốt; không được ép bỏ cờ xác minh bằng mode fast |
| listen | Auto: cảm ơn, đang nói tiếp, partial chưa ổn định, lời của chính bạn hoặc gọi participant khác đã biết | Lưu request `skipped`, không provider/quota, không hủy request thủ công |

Dùng câu hỏi gõ riêng nếu có, nếu không dùng turn mới nhất trong snapshot đã chọn. Turn cũ giúp nhận participant, không tự thay turn mới. Với câu tham chiếu ngắn như “Can we do that?”, xem tối đa ba turn gần nhất để ghi nhận rủi ro; vẫn hỏi xác minh thay vì đoán hành động, và lưu các turn đã dùng trong trigger_segment_ids. Action trên card giữ nguyên lời thoại/nguồn của snapshot card và tạo routing mới cho request mới. Routing gốc không bị sửa.

Thứ tự: nhường lượt trong Auto → xác minh hậu quả/cam kết → mâu thuẫn rõ → action thủ công → so sánh/giải thích → thiếu dữ kiện → trả lời ngắn. Mode thủ công áp dụng sau đó, nhưng không bỏ qua cờ cần xác minh. Số chữ không quyết định luồng. Người nghe cần “Tôi” và speaker label đã quan sát, không suy danh tính khi chưa biết.

## Giao diện

**Chế độ trả lời**: tự phân loại, nhanh, giải thích, sâu, hỏi lại. Chọn mode chỉ áp dụng lần gửi thủ công; Auto vẫn tự phân loại. Preview sau debounce 350 ms, không tạo suggestion/request AI. Preview có thể đổi khi gửi nếu caption/nguồn đổi. Gửi thủ công có thể đáp câu mà Auto đang nhường lượt nghe.

Hiện luồng, lý do, cần xác minh và mục tiêu thời gian. Card đang giữ hiển thị routing snapshot của chính nó. Nút **Phân tích sâu** dùng snapshot card. Kết quả vẫn là schema gợi ý hiện tại, chưa có bảng phương án cấu trúc. Demo vẫn chỉ trả câu hỏi mẫu, không giả lập đã phân tích thật.

## API, lưu trữ và prompt

- `SuggestInput.response_mode`: `auto | fast | explain | deep | clarify`, mặc định `auto`; request cũ vẫn dùng được. Client không được truyền `routing` tùy ý.
- `POST /api/v1/meetings/{id}/classify`: cùng SuggestInput, trả RoutingDecision. Cần active meeting/caption; auth/Host/Origin và segment scope như API hiện tại. Có retrieval nhưng không gọi provider, không thêm ai_request.
- `snapshot.routing`: version, route, automatic_route, source, reasons, risks, evidence_state, requires_verification, trigger_segment_ids, target_min_s, target_max_s, classifier_ms. Giữ cùng request/suggestion snapshot. Snapshot cũ có thể không có routing. Timing không tham gia input_hash; policy version/route có tham gia.
- Provider nhận route/risks/evidence_state/requires_verification và hướng dẫn cố định theo enum. Reasons và trigger IDs gốc không được chèn làm system instruction. Giữ ID aliases và kiểm tra role/evidence/negation/commitment.
- Với cờ cần xác minh, reply có câu trần thuật bị chặn; tối đa một lượt sửa cùng evidence. Đây là kiểm tra hình thức bổ sung, không chứng minh mọi câu hỏi trung lập hoặc mọi claim đúng nghĩa.
- `/api/v1/metrics` có `classifier` (quy tắc trong process, bao gồm preview), `provider_by_route`; provider record có `route`. Connection/report/record cũ có thể thiếu route. Usage chỉ theo provider record, không tính preview/skipped thành model call.

## Mục tiêu và giới hạn

Mục tiêu sau khi có context sẵn: fast 1–2 s, explain 2–4 s, deep 5–10 s, clarify 1–3 s. Không phải timeout/SLA/thời gian im lặng áp dụng mọi cuộc họp. Không cố tình sleep cho đủ khoảng này. Stable của adapter, chờ trigger/scheduler, retrieval, cold start, mạng và render cần đo riêng; debounce 2 s cố định là hành vi lịch sử trước Phase 3.

Số đo 1,498/1,520 giây trước đây thuộc build trước routing, không chứng minh luồng mới đạt mục tiêu. Deep vẫn dùng output budget/timeout live hiện có và lời nói 1–3 câu, chưa là phân tích dài đầy đủ. Khi thiếu self_speaker và nguồn, quy tắc hỏi trung lập vẫn ưu tiên hơn yêu cầu đưa phương án.

Đây là bộ quy tắc Anh–Việt, chưa hiệu chỉnh trên corpus họp thực tế. Có thể sai với câu gián tiếp, trích dẫn, cách nói mới hoặc code-switching. `available` chỉ là có excerpt, không chứng minh đủ bằng chứng; `conflicting` mới nhận metadata/tín hiệu rõ, chưa tìm được mọi mâu thuẫn giữa nguồn. Không trả confidence phần trăm chưa hiệu chuẩn. Không phát hiện kết thúc lượt bằng audio. Guard giai đoạn 1 được áp dụng cho mọi luồng, gồm repair; ba probe gốc đã bị chặn trong [phạm vi hỗ trợ](PHASE1_REPORT.md). Routing không vô hiệu hóa guard, không tạo bộ xác minh ngữ nghĩa tổng quát.

## Kiểm tra

[Fixture Anh–Việt](../fixtures/routing-scenarios.json), [kết quả offline/timing](evidence/routing-review.json), [backend JUnit](evidence/backend-tests.xml), [browser evidence](evidence/e2e-results.json).

Backend kiểm tra auth/scope, preview không provider/job, không bypass xác minh, skip không quota/hủy manual, cache không phụ thuộc timing, prompt/metrics và bounded correction. Browser kiểm tra preview deep, chọn mode/snapshot và preview verification không tăng model count. E2E dùng controlled demo, không chứng minh chất lượng phương án model thật.

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_routing.py
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm run typecheck
npm test
npm run build
npm run test:e2e
```

## Phase 3 — trigger và routing tách vai trò

`content-trigger-v1` quyết định có tạo Auto request hay chờ/bỏ qua; `rules-v1` vẫn chọn route và cờ cần xác minh của snapshot. Không gọi thêm LLM. Câu hỏi ngắn được chờ 150 ms khi rảnh; thông tin/correction 800 ms, batch đầu không quá 2 s. Partial/let-finish chờ lượt ổn định; self/unknown speaker/participant khác không tự đoán cần đáp. Manual ưu tiên, vì thế Auto sau manual chậm đo được 2,9 s, chưa đạt mục tiêu 500 ms mọi câu ngắn.

Focus có thể gồm nhiều câu đang chờ và tiền đề nguyên turn; routing nhìn focus sau cùng, provider thấy toàn bộ focus. Cache xét response_mode/policy/prompt/provider configuration và source/context; pin action giữ snapshot đã chọn. [Báo cáo đầy đủ](PHASE3_REPORT.md) và [review controlled](evidence/phase3/review.json): 0 missed/false trigger trên nhãn replay, không phải accuracy tổng quát. UI hiện chờ người nói/kết thúc, xử lý, tiếp tục nghe, gợi ý mới, quota hoặc stale; reason codes ở metrics/API.
