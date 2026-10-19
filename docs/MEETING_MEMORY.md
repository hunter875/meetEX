# Bộ nhớ cuộc họp hiện tại

`meeting-ledger-v1`, Phase 4 **PARTIAL**. [Schema/state/cadence/budget, đánh giá và giới hạn](PHASE4_REPORT.md). Đây là ledger evidence trong một meeting, không knowledge graph hoặc bộ nhớ suy luận xuyên project.

Luồng dữ liệu: caption revision → archive nguyên văn → incremental stable extraction → reconcile cùng meeting → memory versions → live snapshot / report snapshot. Partial correction vô hiệu hóa dependency ngay. Không đưa model summary trở lại làm evidence, không extraction LLM mỗi caption.

| API | Hành vi |
| --- | --- |
| GET `/api/v1/meetings/{id}/memory` | revision/policy/items, gồm history state; origin phân biệt transcript/user_edit |
| GET `/api/v1/meetings/{id}/memory/{item_id}/history` | immutable versions cùng meeting |
| GET `/api/v1/meetings/{id}/evidence/{segment_id}?revision=N` | raw revision đúng scope; thiếu legacy archive trả 404, không bịa |
| PATCH `/api/v1/meetings/{id}/memory/{item_id}` | expected_version + text/owner/raw_due_text/status; conflict 409; origin luôn user_edit |
| POST `/api/v1/meetings/{id}/memory` | ghi chú người dùng, kind/status hợp lệ, không giả speech/evidence |
| POST `/api/v1/meetings/{id}/memory-rebuild` | explicit rebuild từ current stable captions; giữ user edits, không khôi phục được revisions legacy chưa lưu |

Tất cả API vẫn Bearer/Host/Origin loopback như cũ. Item ID không cho phép vượt meeting/project. Caption không ổn định không tạo extraction request. UI “Bộ nhớ có bằng chứng” nằm trong Live/Report; không yêu cầu xác nhận mọi item.

Live có structured memory và raw evidence, tổng budget hữu hạn, memory_revision tham gia cache/freshness. Current gồm cancellation tombstone/disputed, không gồm node bị thay thế. Project source facts vẫn dùng source/generation/citations, không xác nhận participant owner/deployment. AI proposals ở phần riêng. User edit được quy nguồn và không thành participant acceptance.

Report maps giữ guard/retry/repair cũ, rồi đối chiếu current/history bằng ledger, không thêm model synthesis. Report lưu evidence/memory snapshot và version riêng; sửa/caption revision sau đó chỉ cảnh báo, không sửa ngầm bản cũ. Markdown/JSON có owner/due/state/origin/evidence revisions/history. Legacy ReportItem normalized_due vẫn giữ grammar cũ; normalized relative dates nằm trong memory snapshot kèm rule/anchor.

Migrations 001→002 chạy một lần theo schema_version, local/RAM cùng schema; không reset DB. Dữ liệu cũ không được tự nâng verified. Xóa meeting/project/retention cascade item/versions/archive/reports; RAM mất khi restart. Query cache dùng digest và bị evict/fence khi xóa; worker đang chạy hoàn tất read rồi bỏ kết quả, không ghi query xuống disk.

Bare Yes, authority, paraphrase, multilingual extraction, factual contradictions tổng quát và report completeness ngoài grammar chưa được xác minh. [Đánh giá synthetic](evidence/phase4/review.json) không là accuracy model thật. [Phase 5](NEXT_PRIORITIES.md) tập trung CI/refactor/setup-update/migration/operational validation.
