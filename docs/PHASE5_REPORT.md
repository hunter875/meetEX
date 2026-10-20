# Phase 5 — bảo trì và vận hành local

**Release candidate để thử nội bộ, 2026-10-20.** Implementation Phase 5 đã qua phạm vi kiểm chứng dưới đây. Version **0.1.0 / protocol 1 / schema 2**, branch `codex/phase5-local-operations`. Không phải production-ready hoặc MVP VERIFIED; live/independent gates còn mở. Paid provider calls mới: **0**. Các phép đo lưu timestamp UTC riêng, không đổi ngày evidence lịch sử.

| A–F | Kết quả | Phạm vi |
| --- | --- | --- |
| A. Maintainability | PASS trong phạm vi | Migration/ownership/backup/runner/report export; bounded format/lint và inert import. Không tuyên bố đã refactor toàn bộ legacy service/ledger |
| B. Operations | PASS Windows đã thử | CLI thống nhất, OS lock, verified start/stop/restart/doctor; port conflict/foreign process/stale PID/crash/shutdown stream+index có tests |
| C. Upgrade/recovery | PASS các đường đã thử | Schema 1 → 2, schema 2 reopen, WAL backup/restore/preimage/fault; clean update/reinstall giữ mọi application row và report edit |
| D. Pairing | PASS automated | Token cũ REST 401/WS đóng 4401; pair token mới; MV3 UI disconnect xóa credential/state, dừng reconnect; protocol mismatch có test |
| E. CI/artifact | PASS phạm vi bàn giao | Windows Server 2025 + Ubuntu 24.04, Python 3.13/Node 22.20.0; locked build, source/extension ZIP và manifest local; không publish release |
| F. Handoff | PASS controlled | Clean clone trên account/máy phát triển đã có runtime, 60 phút soak và 10 phút fault metrics; Windows desktop/account/VM độc lập vẫn NOT TESTED |

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

Token entropy 32 bytes; atomic file + Windows account ACL/POSIX 0600; rotation đóng WS cũ 4401 và REST cũ 401, không đổi meeting/provider key. Extension disconnect xóa credential/state tạm và dừng reconnect; các trang extension đang mở đồng bộ xóa token qua heartbeat 2 s, không cần reload. Poll không ghi đè form đang nhập khi config chưa đổi; cả hai có browser regression. Invalid auth yêu cầu re-pair; version/protocol mismatch có nhãn. [Ctrl+C native Windows](evidence/phase5/ctrlc.json) đã thử qua entry công bố: shutdown hoàn tất, active meeting thành interrupted, lock thả và runtime metadata xóa. Đã chặn traceback KeyboardInterrupt ở runner; Python dùng interrupt exit 130, PowerShell ConPTY của bài thử trả interrupted-pipeline exit 1.

## Tái tạo và bàn giao

Lệnh chạy được nằm trong [README](../README.md) và [runbook](LOCAL_OPERATIONS.md), kiến trúc ở [ARCHITECTURE](ARCHITECTURE.md). `python scripts/meet.py test --browser` chạy backend/frontend/typecheck/build/contracts/lint/format, đủ semantic probes, orchestration replay, toàn corpus memory và browser E2E; output `.local/checks`. CI dùng cùng entry qua redactor, không paid secrets, không skip browser thành green; trace/HAR không upload vì có thể chứa credential. Workflow không thay branch protection từ xa; chủ repo có thể đặt required checks riêng.

Kết quả cuối: **349 backend / 63 frontend / 7 browser E2E**, không failure/skip; [JUnit](evidence/phase5/backend-final.xml), [frontend](evidence/phase5/frontend-final.json), [browser](evidence/phase5/browser-final-results.json), [log](evidence/phase5/checks-final.log). [Semantic](evidence/phase5/semantic-regression.json) 82 fixture và ba probe gốc đều qua trong grammar; [memory](evidence/phase5/memory-regression.json) 38/38 item/evidence, 0 sai/thừa/thiếu; [orchestration](evidence/phase5/orchestration-regression.json) 39/39 eligible, missed/false trigger 0, logical 40 / HTTP 42. Không đổi mục tiêu Phase 3 để gọi PASS.

CI [run 39430598033](https://github.com/hunter875/meetEX/actions/runs/39430598033) PASS cả hai OS, source `d7796da5e9a7e6b2794c2ea44ba9545d7da710ca`; [metadata](evidence/phase5/ci-result.json). Local: Windows 11 build 26200, Python 3.13.4, Node 22.20.0, FTS5; CI Python 3.13.16. Một warning Starlette/anyio và dependency deprecation còn tồn tại, không làm checks fail.

CI đầu bắt thiếu NumPy trong test profile và POSIX venv symlink bootstrap; đã pin NumPy 2.5.4 trong dev lock, E5/Torch vẫn tùy chọn. CI sau bắt alias ubuntu-latest chuyển sang Ubuntu 26.04 không hỗ trợ Playwright đang khóa: pin OS 24.04/Windows 2025. [Log bootstrap lỗi](evidence/phase5/ci-bootstrap-fail.log), [OS alias lỗi](evidence/phase5/ci-os-alias-fail.log) giữ riêng. Clean clone bắt cold NumPy import vượt barrier 2 s của test giữ worker: preload dependency trước barrier, giữ nguyên assertions ACK <500 ms/generation/thread; không sửa guard hoặc bỏ case.

Upgrade fixture schema 1 chứa project/source/chunks/FTS, transcript và user-edited report versions/parent; migrate giữ mọi hàng schema 1, không bịa archive trước schema 2. Schema 2 backup online qua WAL, restore so sánh mọi application row, kiểm revision archive/memory/version/report edit. FK/index/FTS query còn hoạt động. Lỗi migration rollback, schema mới hơn bị từ chối trước WAL; lỗi replace restore giữ current và preimage. RAM meeting không vào backup, token/key/env/cache không chuyển máy. Xem tests operations và evidence cuối.

Clean rehearsal [PASS](evidence/phase5/clean-setup.json), source `a15bf0a174a986ac99c106d0e13acb0215e7d5f0`: clone mới có khoảng trắng trong path, không venv/node_modules/data sẵn; setup/build/start/health/doctor, 12 nguồn demo, meeting/report/edit/export, rotation, online backup, mutate/stop/restore/restart, update/reinstall, so sánh fingerprint mọi application row và chạy toàn bộ tests. Pip/npm/Playwright download caches có thể dùng chung; browser profile test là mới. Đây là clean folder trên account đã có runtime, **không phải Windows desktop sạch**. Tái tạo bằng `python scripts/clean_phase5.py` với destination mới. Các candidate lỗi giữ riêng, không tính PASS.

Soak đặt trước: 3600 s, caption/2 s, recycle/60 turns, reconnect/10 turns; giới hạn lấy mẫu RSS ≤768 MiB và SQLite/WAL ≤256 MiB, temp synthetic data. [60 phút](evidence/phase5/soak-final-60m.json): **3600,374 s, 1.750 caption, 175 reconnect, 30 report/117 maps, 233 lượt suggest, 350 provider attempts**, harness error 0, shutdown PASS. Có chủ động chèn 18 HTTP 429, 8 HTTP 401 và 20 slow timeout. RSS sau vòng tối đa 67,64 MiB, cuối 32,75 MiB; DB/WAL tối đa 5,24 MiB. Sau xóa mỗi project: report jobs/query/vector cache về 0; metadata buffers bị chặn kích thước. Đây là sampled working set, không tuyên bố đã đo mọi đỉnh RSS.

[10 phút bổ sung](evidence/phase5/soak-outcomes-10m.json) trên các module ASGI có hash trùng bản bàn giao: 293 caption, 39 suggest → 32 ready / 7 error do fault injection (4 rate limit, 1 auth, 2 timeout); 59 HTTP attempts, 20 report maps; active generation tối đa 1, unknown usage 59. Riêng runner entry point được bổ sung guard Ctrl+C sau soak và đã kiểm tra riêng như trên; harness ASGI không chạy entry point đó. Không gọi error fraction 7/39 là tỷ lệ lỗi tự nhiên. ACK synthetic 60 phút median 12,91 ms/p95 24,39 ms là WS→apply→ACK trong harness, **không phải speech-to-UI hoặc model latency**. Capture liên tục/reconnect/reindex/report/delete nằm trong ASGI soak; restart/process và mở/đóng panel nằm trong process/clean/browser suites riêng. E5 và Google Meet thật không được giả bằng loop này. Candidate soak bị dừng để sửa source không tính PASS.

Package local từ exact Git commit sạch, npm ci/build trong temp mới; source/extension ZIP có thứ tự/timestamp cố định, manifest SHA256 và build-info. Version 0.1.0/protocol 1/schema 2; source commit chính xác nằm trong manifest đi kèm, BUILD_SOURCE.json và extension/build-info.json. Bản bàn giao ở `.local/artifacts/phase5-delivery`; metadata/checksum và kiểm tra archive ở `docs/evidence/phase5/artifact-manifest.json` / `artifact-audit.json`. Source build commit có thể đi trước commit chỉ bổ sung evidence; mọi file app được đối chiếu hash. Không publish release, push tag hay upload source/extension artifact công khai.

## Release gates

| Gate | Trạng thái hiện tại |
| --- | --- |
| Core correctness | PASS regression hiện có; PARTIAL ngoài grammar/alias |
| Meet capture thực tế | NOT TESTED |
| Provider quality thực tế build mới | NOT TESTED |
| Long meeting/report | PARTIAL, controlled only |
| Performance/cost | PARTIAL; không SLA 1,5 s, token/cost thật unknown |
| Upgrade/recovery | PASS các đường fixture và clean update/recovery đã thử |
| Clean Windows account/VM | NOT TESTED |
| Operational soak | PASS controlled 60 + 10 phút; thực địa/E5 NOT TESTED |

Kết luận: **đủ làm release candidate để thử nội bộ**, hoàn tất implementation Phase 5 trong phạm vi ghi trên; chưa nghiệm thu đầy đủ bản local cho họp thật. Cần đóng Meet hai participant, chất lượng/chi phí provider build mới với budget được cấp, Windows desktop độc lập và vận hành E5/thực địa. CI xanh và clean folder không thay các gate này.
