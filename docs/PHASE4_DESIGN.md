# Phase 4 — schema và quy tắc trước triển khai

Baseline: `codex/phase3-orchestration` / `af868491a77a168e3ab68b457bb6a10c65f0c3f7`, worktree sạch. Nhánh thực thi `codex/phase4-meeting-memory`. Phase 3 PARTIAL và live gates chưa đóng; không có budget provider mới.

Memory item scoped meeting/project, ID ổn định theo segment + clause slot (user-created dùng UUID), version tăng; kind, text nguyên mệnh đề, entity/task, action, environment, speaker, owner/candidate owner, raw_due_text, normalized_due + anchor/rule/uncertainty, origin, evidence `{segment_id, revision}`. Chỉ transcript revisions gốc là evidence. Lưu revisions caption và versions memory trong đúng DB local/RAM, FK cascade. Không nâng dữ liệu cũ thành verified. Migration 002 chạy một lần theo schema_version, không reset DB.

Loại và state tối thiểu: requirement requested/withdrawn; proposal proposed/accepted/rejected; decision unconfirmed/confirmed/disputed/superseded/cancelled; action_item requested/accepted/completed/disputed/superseded/cancelled; open_question open/resolved; spoken_fact stated. invalidated cho item mất revision evidence. Project facts ở source retrieval riêng; AI proposals và user edits không được giả thành participant speech.

Chuyển trạng thái có evidence: cùng exact task/action/environment mới được liên kết. Proposal mới không thay confirmed. Cùng speaker sửa rõ bằng correction/change/instead có thể supersede; cancellation rõ liên kết đúng đối tượng; người khác phủ nhận/phát biểu trái nhau giữ disputed khi chưa đủ căn cứ giải quyết. Bare Yes không tự chọn một trong nhiều antecedents. Nhận việc chỉ từ chính speaker có câu nhận rõ đúng task; request/can/reported/quoted/conditional không phải acceptance. Đổi owner cần self-acceptance và nêu rõ take-over/from owner cũ. Không tự coi latest luôn thắng. Giữ quan hệ và versions trước đó.

Caption partial không extraction; correction/speaker change vô hiệu hóa evidence cũ ngay. Stable revision được parse lại và reconcile deterministic; không extraction LLM. Grammar hỗ trợ tiếng Anh explicit task IDs và một số cấu trúc đã công bố; không hứa entailment/coreference tổng quát. Unsupported speech vẫn còn nguyên trong transcript và report maps, không tự bịa item quan hệ. Gap luôn được đưa vào report, không suy đoạn xác nhận chưa quan sát.

Deadline: raw giữ nguyên; ISO date hợp lệ hoặc tomorrow dựa trên observed_at của evidence trong timezone meeting, không ngày mở report. Maybe/next Friday/early next week mơ hồ không chuẩn hóa. Ngày nói tới không tự thành due. Deadline overdue không đổi task state.

Live: chọn items còn hiệu lực và disputed có liên quan, budget item + evidence nguyên turn; memory revision tham gia snapshot/cache/freshness. Superseded/cancelled có tombstone khi liên quan để tránh hồi sinh qua câu cũ. Project/meeting khác tuyệt đối tách.

Report: map/repair cũ vẫn validate; thêm reconciliation deterministic theo memory evidence/task trước validate cuối. Tách current khỏi history, summary không nối lại các confirmation cũ đã hết hiệu lực. Lưu memory/evidence snapshot immutable với report version; user edit có provenance và conflict handling riêng, regenerate tạo bản mới không ghi đè bản đã sửa. Output không biểu thị model confidence như bằng chứng.

Đánh giá: corpus có nhãn tạo trước tuning, 18 nhóm bắt buộc + held-out biến thể; precision/recall item/owner/due/confirmation/relations/evidence tính riêng, không gọi pass fixture là accuracy thật. Long transcript hàng trăm turns/nhiều maps, controlled provider; đo memory delay/ACK/report attempts, không paid calls. Mục tiêu bắt buộc: không current cancelled/superseded, không gán chéo owner/due trong corpus; unsupported grammar phải báo giới hạn.
