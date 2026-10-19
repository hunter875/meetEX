# Phase 5 — bảo trì và vận hành local

**Implementation awaiting validation, 2026-10-19.** Candidate 0.1.0 / protocol 1 / schema 2. Không phải production-ready hoặc MVP VERIFIED. Bản này đang được kiểm chứng; bảng dưới sẽ cập nhật từ evidence cuối. Paid provider calls mới: **0**.

| A–F | Trạng thái tạm | Phạm vi |
| --- | --- | --- |
| A. Maintainability | PARTIAL | Ranh giới migration/ownership/backup/runner/report export; format/lint có phạm vi, lifecycle inert; chưa refactor toàn bộ legacy service/ledger |
| B. Operations | PARTIAL | CLI thống nhất; OS lock, verified shutdown/readiness/doctor; tests process đã chạy, clean setup đang kiểm chứng |
| C. Upgrade/recovery | PARTIAL | Schema 1 → 2, reopen, WAL backup/restore/current preimage/fault tests đã chạy; update clean candidate còn kiểm chứng |
| D. Pairing | PARTIAL | REST/WS rotation unit/integration; UI disconnect/compatibility; browser retest đang chạy |
| E. CI/artifact | PARTIAL | Windows/Ubuntu workflow, locks, timeout/least permissions, redacted failure artifacts; chưa có remote outcome/artifact cuối |
| F. Handoff | PARTIAL | Checklist/runbook; clean checkout và soak cuối đang chạy; Windows account/VM độc lập NOT TESTED |

## Đầu vào và gate mở

Branch đầu `codex/phase4-meeting-memory`, commit `9a5ac7153343a4b84256fbc1343267eeb285de55`, working tree sạch; không có AGENTS.md trong checkout/parent. Thực hiện ở `codex/phase5-local-operations`. Đã đọc README, báo cáo Phase 1–4 và source thực tế. Baseline **331 backend / 60 frontend**: [backend](evidence/phase5/baseline-backend.xml), [frontend](evidence/phase5/baseline-frontend.json).

| Phân loại | Phát hiện đầu vào | Cách xử lý |
| --- | --- | --- |
| Chặn bàn giao vận hành | Import schema tạo token/mở DB/retention/interrupted; không có process ownership; thiếu restore an toàn | Chuyển sang lifespan, OS lock, migration fail closed và SQLite backup/atomic restore |
| Có workaround | Stop khi thread index/model đang chạy có thể chậm; extension đổi path/profile có thể đổi ID | Giữ lock, báo timeout thật; End trước update, giữ unpacked path, kiểm ID/Origin và re-pair |
| Giới hạn công bố | Grammar/alias bounded; bare Yes/authority/coreference, weighted matrix, semantic/cost/general accuracy chưa hoàn chỉnh | Giữ guard và kết luận PARTIAL các phase trước; không thêm cloud/multiuser |
| Chưa kiểm thử | Meet hai participant, model quality/cost build mới, Windows độc lập, E5 soak | Giữ NOT TESTED, checklist cụ thể |

[Phase 1](PHASE1_REPORT.md), [Phase 2](PHASE2_REPORT.md), [Phase 3](PHASE3_REPORT.md), [Phase 4](PHASE4_REPORT.md) giữ nguyên lịch sử. Phase 3 vẫn chưa đạt reduction 20%/Auto wait 500 ms; không dùng Phase 5 để đóng lại mục tiêu đó.

## Thay đổi và hợp đồng

ASGI/OpenAPI import không tạo tài nguyên/credential, không đổi environment hoặc meeting. Lifespan giành OS lock rồi khởi tạo; shutdown hủy tasks, đóng stream, đợi worker trước DB/lock. Tách migration, ownership, backup, runner và Markdown export. Format main/config/storage và ba frontend module đã chạm; linter pin Ruff 0.14.1, Prettier 3.6.2. Không hứa toàn bộ legacy source đã đạt full style lint.

CLI stdlib bootstrap chọn Python venv đúng Windows/POSIX, paths theo script/project, lockfiles, runtime/FTS errors rõ. Thin PowerShell wrappers giữ entry cũ. Start reserve port trước data init, stop xác minh instance+auth và OS lock, không tin PID, không kill foreign app. `/health` giữ response cũ; thêm `/ready`, authenticated shutdown/rotate. OpenAPI và TypeScript cập nhật tương thích thêm.

Report thêm một job toàn cục, REPORT_BUSY 429, 300 s tổng chờ provider / mặc định 90 s/map / 64 maps; deadline không xóa saved versions. RAM report jobs giới hạn khoảng 200 completed entries; history DB giữ theo retention.

Token entropy 32 bytes; atomic file + Windows account ACL/POSIX 0600; rotation đóng WS cũ 4401 và REST cũ 401, không đổi meeting/provider key. Extension disconnect xóa credential/state tạm và dừng reconnect; invalid auth yêu cầu re-pair; version/protocol mismatch có nhãn.

## Tái tạo và bàn giao

Lệnh chạy được nằm trong [README](../README.md) và [runbook](LOCAL_OPERATIONS.md), kiến trúc ở [ARCHITECTURE](ARCHITECTURE.md). `python scripts/meet.py test --browser` là bộ kiểm tra chung; output `.local/checks`. CI chạy cùng bộ lệnh qua redactor, không paid secrets, không skip browser thành green; trace/HAR không upload vì có thể chứa credential. Workflow không thay branch protection từ xa.

Upgrade fixture schema 1 chứa project/source/chunks/FTS, transcript và user-edited report versions/parent; migrate giữ mọi hàng schema 1, không bịa archive trước schema 2. Schema 2 backup online qua WAL, restore so sánh mọi application row, kiểm revision archive/memory/version/report edit. FK/index/FTS query còn hoạt động. Lỗi migration rollback, schema mới hơn bị từ chối trước WAL; lỗi replace restore giữ current và preimage. RAM meeting không vào backup, token/key/env/cache không chuyển máy. Xem tests operations và evidence cuối.

Soak đặt trước: 3600 s, caption/2 s, recycle mỗi 60 turns, reconnect/10 turns, report nhiều map, source/reindex/search, controlled provider 429/401/slow timeout; RSS ≤768 MiB và SQLite/WAL ≤256 MiB. Dùng temp synthetic data, ghi ACK/RSS/task/listener/cache/disk/attempts; không giả Chrome panel/Meet/model thật. Các candidate soak bị dừng để sửa source được giữ riêng và **không tính PASS**. Bản soak cuối chưa kết thúc tại thời điểm ghi này.

Package chỉ local từ exact Git commit sạch, npm ci/build trong temp mới; source/extension ZIP deterministically ordered, fixed ZIP timestamps và checksums/manifest/build-info. Không publish release, tag hoặc upload artifact công khai. Artifact/version/source commit cụ thể được ghi sau kiểm chứng.

## Release gates

| Gate | Trạng thái hiện tại |
| --- | --- |
| Core correctness | PARTIAL ngoài grammar; regression cuối đang chạy |
| Meet capture thực tế | NOT TESTED |
| Provider quality thực tế build mới | NOT TESTED |
| Long meeting/report | PARTIAL, controlled only |
| Performance/cost | PARTIAL; không SLA 1,5 s, token/cost thật unknown |
| Upgrade/recovery | PARTIAL tới khi evidence cuối tổng hợp |
| Clean Windows account/VM | NOT TESTED |
| Operational soak | RUNNING, không gọi PASS trước khi xong |

Kết luận tạm: implementation awaiting validation, chưa nghiệm thu bản local. Các phần chưa chạy không được thay bằng log máy phát triển rồi gọi Windows sạch.
