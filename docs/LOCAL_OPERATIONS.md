# Vận hành local và khôi phục

Trạng thái nghiệm thu duy nhất: [Phase 5](PHASE5_REPORT.md). Lệnh: [README](../README.md); kiến trúc: [ARCHITECTURE](ARCHITECTURE.md). Entry point resolve theo vị trí script; data path tương đối tính theo project. Có thể gọi từ cwd khác: `python 'D:\Meet Copilot\scripts\meet.py' doctor --data-dir 'D:\Meet Data'`.

## Start, stop, crash

Chỉ một worker; không dùng reload/multiple Uvicorn workers. Start reserve port trước khi chạm dữ liệu. OS byte lock `writer.lock` (Windows msvcrt / POSIX flock) quyết định ownership; file còn sau crash không chứng minh writer còn chạy. Không xóa lock để vượt ownership. Startup giành lock trước token, migration, retention và phục hồi meeting. Runtime metadata chỉ chứa PID tham khảo và instance nonce.

Stop đối chiếu instance `/ready` với runtime.json, gọi HTTP có bearer token và nonce; không kill theo PID. Chờ OS lock được thả mới báo stopped. Metadata bị sửa hoặc port không thuộc instance → từ chối. Uvicorn trực tiếp không có stop monitor của runner: bản công bố dùng `meet.py start`; direct Uvicorn chỉ cho test/development, dừng Ctrl+C.

Shutdown đánh dấu not ready, đóng WS, hủy scheduler/provider/report tasks, đợi thread index/retrieval rồi đóng DB và thả lock. Index/model download không force-preempt an toàn: stop có thể timeout 40 s và báo chưa dừng; giữ ownership tới khi worker xong. Đợi E5 download hoàn tất trước update. Crash giải phóng OS lock; restart local active/paused thành interrupted, giữ transcript/report; RAM sessions mất. Retention vẫn áp dụng khi startup và mỗi 15 s, độc lập với migration.

`/health`: liveness, contract cũ. `/ready`: startup, app/protocol/schema, keyword/semantic/key-present capability và instance ID; không chứa credential/transcript. Có key không chứng minh provider dùng được. Doctor không thực hiện paid request.

## Chẩn đoán

| Hiện tượng | Thao tác |
| --- | --- |
| Không kết nối | Doctor; start trong terminal riêng; xem lỗi startup. Kiểm tra đúng data directory/port 8765. |
| Port bị chiếm / PROCESS_UNVERIFIED | Xác minh ứng dụng bằng công cụ Windows; tự dừng ứng dụng đó. Script không kill foreign PID. |
| DATA_BUSY | Stop writer đúng instance. PID file cũ không cần xóa để vượt lock. |
| Pairing / 401 | Đọc token hiện tại và lưu kết nối lại. Doctor xác nhận token local của directory, không đọc Chrome storage. |
| Origin / 4403 | Copy ID ở chrome://extensions, chạy pair-extension.ps1, restart backend. Exact Origin/Host vẫn bắt buộc. |
| Không caption | Bật caption, chọn đúng vùng/speaker/tab/meeting; đợi lượt mới; xem unsupported/unknown/disconnected. Không chọn chat. |
| Provider 401/429/timeout | Key provider riêng ở RAM/environment; sửa key/chờ quota, thử thủ công. Không tự fallback demo để báo success. |
| REPORT_BUSY / REPORT_DEADLINE | Đợi report trước. Một report toàn cục, 64 maps tối đa, 90 s/map mặc định và 300 s tổng chờ provider. Bản đã lưu còn nguyên. |
| Schema mới hơn app | Matching source hoặc backup trước upgrade; không reset DB/sửa schema_version để ép chạy. |
| Migration lỗi | Backend không ready; giữ DB, validate backup. Migration lỗi rollback transaction; migration hoàn tất không chạy lại. |
| Thiếu FTS5/dependency | Official Python có FTS5; setup từ runtime hỗ trợ. Thiếu E5 không chặn keyword. |
| Data dir không ghi được | Chọn directory thuộc tài khoản của bạn hoặc sửa đúng ACL; không chạy admin để né lỗi. |

Doctor kiểm tra runtime/modules/FTS5, disposable file về quyền ghi, schema read-only, port/readiness/instance/token local, Origin cấu hình và semantic module tùy chọn. Không sửa DB, xóa lock, rotate credential hay tải model. WARN = chưa cấu hình/chưa chạy; FAIL exit 1. JSON không chứa token/key/transcript/source excerpt. Có thể lưu `python scripts/meet.py doctor > doctor.json`, xem lại trước chia sẻ. Có module E5 vẫn cần nạp model chủ động; doctor không chứng nhận inference.

## Backup/restore

1. Backup vào directory mới có thể chạy khi backend mở. SQLite backup API lấy consistent snapshot, integrity/FK checks, manifest app/schema/time/counts/SHA256. Snapshot timeout 30 s; lỗi không sửa source, không ghi đè backup cũ.
2. Gồm project/source metadata/chunks/FTS, local transcript/revisions, memory/history, report versions. Không RAM/token/provider key/.env/model cache hoặc external source files. Repo/CSV ngoài DB cần sao lưu riêng để reindex sau chuyển máy.
3. Stop rồi restore. Validate manifest/checksum/schema/integrity/FK trước khi thay target; ownership lock từ chối active writer.
4. Staging/validate cùng filesystem, giữ current DB ở `recovery/TIMESTAMP-RANDOM`, checkpoint WAL cũ rồi atomic replace. Lỗi trước replace giữ current DB; crash sau replace có DB mới hoàn chỉnh và preimage. Không trộn WAL cũ với DB mới. Staging còn sau lỗi không có nghĩa restore thành công.
5. Start/doctor; kiểm tra project, caption revisions, report user edit/evidence. Retention có thể xóa meeting hết hạn khi start; backup giữ snapshot trước đó.

Token/Origin không đi theo backup. Restore cùng máy giữ token hiện tại; directory/máy mới tạo token mới và phải pair. API key chỉ RAM/environment. Backup chứa dữ liệu cuộc họp: lưu trong directory chỉ tài khoản của bạn truy cập. Token được private theo Windows account ACL hoặc POSIX mode 0600. Doctor export không kèm backup.

Đã có fixture schema 1 → 2 và schema 2 reopen/backup/restore, rollback migration lỗi, future schema từ chối. Không hứa mọi phiên bản lịch sử. Rollback source chỉ an toàn khi source cũ hỗ trợ schema hiện tại; nếu không, restore pre-upgrade backup và chấp nhận mất thay đổi sau snapshot. Không tự downgrade schema.

## Update và build

End, stop, lưu thay đổi source riêng và chọn target commit bằng Git hoặc giải nén archive. Update giữ pre-upgrade backup, setup locks, build, migrate/validate trong ownership lock. Không fetch/reset Git tự động hoặc xóa DB. Setup/build lỗi giữ backup/dữ liệu; sửa runtime và chạy lại với destination mới.

Reload extension cùng unpacked path/profile thường giữ ID và chrome.storage.local config/profile. Đổi path/profile có thể đổi ID: kiểm tra lại, allowlist và pair exact Origin. Không có manifest key bảo đảm ID xuyên máy. Reload worker làm capture không chắc chắn; update sau End. chrome.storage.session là tạm, không hứa giữ qua reload. Backend vẫn phục vụ protocol 1 cũ; extension mới kiểm `/ready` + app/protocol, chặn backend thiếu/sai khả năng và yêu cầu update đồng bộ.

Package đòi tracked tree sạch; archive exact HEAD, npm ci/build trong temp độc lập, source.zip + extension.zip + manifest/checksums. Extension có build-info.json, source có BUILD_SOURCE.json. Không tag/publish/upload release. Chỉ review artifact local, không phát hành source_clean=false.

## Kiểm tra và clean Windows gate

Setup rồi test --browser: backend (migration/backup/restore, Phase 1–4), frontend, TypeScript/build, contract, Ruff/Prettier, Chromium E2E với DOM synthetic/controlled SSE. Output ở `.local/checks`, không ghi đè evidence lịch sử. Keyword CI không đại diện semantic/model/Meet thật. CI không cần provider secret; console/artifact text được redacted, không xuất trace/HAR có thể chứa token; screenshots chỉ synthetic.

Ruff syntax/undefined-name checks toàn backend. Formatter/full E4/E7/E9/F giới hạn main/config/storage và module vận hành mới/refactor; Prettier giới hạn background/api/settings đã sửa. Không tuyên bố format/lint toàn bộ legacy code, không ignore toàn thư mục để xanh giả.

Clean checkout trên máy đã có runtime khác account/VM Windows mới. Gate độc lập: cài Python/Node/Chrome ở account/VM mới; checkout đúng commit; setup/build/start/doctor; Load unpacked/pair; demo source/meeting/report/edit/export; stop/restart; backup/restore; update/re-pair; Meet với hai participant được phép. Ghi OS/runtime/commit, output đã redacted và PASS/FAIL từng bước. Chưa chạy giữ NOT TESTED.
