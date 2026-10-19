# Kiến trúc hiện tại

**0.1.0 / protocol 1 / schema 2.** Trạng thái: [PHASE5_REPORT](PHASE5_REPORT.md); thao tác: [LOCAL_OPERATIONS](LOCAL_OPERATIONS.md). Không suy hoàn tất từ spec ban đầu.

| Thành phần | Trách nhiệm |
| --- | --- |
| extension/content | DOM profile đã hiệu chuẩn; speaker/turn/revision/stable heuristic; đúng tab/document/meeting; không audio/backfill |
| extension/background | Binding, outbox RAM giới hạn, WS auth/ACK/retry/idempotency, sender checks, reconnect/disconnect |
| extension/ui | Năm màn hình; giữ card/queue, evidence, memory annotation, report edit/version/export |
| app/main | API/Host/Origin/auth và WS; ASGI/OpenAPI inert, tài nguyên khởi tạo trong lifespan |
| service + orchestration/routing | Classifier local, pending focus, manual ưu tiên, coalescing/dedup/cache/freshness, task/timer/report lifecycle |
| llm + evidence | Provider SSE/pooling/retry/repair/usage; schema/evidence guards trước publish; không general entailment |
| ingestion + retrieval | Preview/import snapshot, FTS5, optional pinned E5 CPU; worker/cache/index generation và deletion fence |
| meeting_memory + report_ledger/report_export | Ledger revision/state/provenance; user edit tách speech; current/history; Markdown tách API |
| storage + migration | SQLite WAL/FK/FTS5 và RAM DB; transaction/idempotency/retention; ordered migration một lần, fail closed |
| ownership + runner/backup | OS data lock, verified shutdown, private atomic token; SQLite backup và stopped atomic restore |
| scripts/meet.py | setup/build/start/stop/doctor/test/backup/restore/rotate/update/package từ locks |

Caption DOM → raw revision reducer → bounded outbox → WS scoped auth/bind → SQLite apply/ACK → trigger/classifier → scheduler → context/retrieval/memory → buffered SSE → schema/evidence/state validation → store/event → UI. Correction có thể invalidate memory/card; pin giữ snapshot cũ có nhãn stale.

Import đọc repo/text/schema/CSV/JSON như dữ liệu không tin cậy, áp dụng allow/skip/size boundaries rồi publish index generation/chunks/FTS/vector. Không execute code/SQL hoặc live connector production. E5 chưa loaded vẫn keyword, có nhãn.

Một active/paused meeting toàn process, RAM hoặc local. Pause không capture, resume không backfill; End flush/ACK có cảnh báo khi thiếu; crash local thành interrupted, RAM mất. Một process/worker sở hữu data directory bằng OS lock. Một live generation active/latest queued; một report toàn cục, tối đa 64 maps, budget provider tổng 300 s và mặc định 90 s/map. Report jobs trong process giữ tối đa khoảng 200 mục hoàn tất; DB history giữ theo retention/xóa phiên.

Project/source nằm disk; RAM meeting không được ghi disk/backup. Ledger giữ raw evidence revision và origin; user annotations không trở thành lời participant. Report ghi immutable snapshot/current/history; regenerate thêm version, giữ user edits cũ. Grammar Anh/alias có giới hạn, chưa đầy đủ authority/coreference/multilingual hoặc weighted decision matrix.

Pairing token entropy 32 random bytes, private atomic file; bearer REST/first-frame WS, exact Origin/loopback Host. Rotation cần token hợp lệ hoặc CLI offline giành OS lock, không đổi meeting/provider key; WS cũ đóng 4401. Invalid auth dừng reconnect tới khi pair lại. Disconnect xóa credential/outbox/card tạm, giữ profile. Provider key chỉ RAM/environment; readiness/doctor không in giá trị key/token hoặc nội dung họp.

Retention/xóa project/meeting cascade DB archive/ledger/report; source xóa giữ nhãn evidence snapshot lịch sử, xóa active index. Worker cũ không repopulate cache đã xóa. Không cam kết forensic erasure trên SSD/swap/backup ngoài ứng dụng. Restore không import token/key.

Giới hạn: không multiworker/multiuser/cloud; thread index/model không force-preempt, có thể làm stop chậm và phải giữ lock; guard không thay người xem lại. Meet DOM heuristic chưa nghiệm thu hai participant thật. CI xanh không đóng gate thực địa/model/cost/Windows độc lập.
