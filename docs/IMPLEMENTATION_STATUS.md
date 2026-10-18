# Trạng thái triển khai theo task

Ngày bàn giao: 2026-10-17 · app 0.1.0 · Windows local. IMPLEMENTED không đóng gate live. Spec gốc vẫn giữ status TODO như tài liệu đầu vào.

| Task | Nội dung | Trạng thái / bằng chứng |
| --- | --- | --- |
| T-001 | Khởi tạo repo, dependency lock và baseline runtime | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-002 | Pairing và loopback API/WS auth | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-003 | Inspect Meet và adapter version đầu | PARTIAL · calibration chạy với DOM synthetic; DOM/selector Meet thật chưa xác minh |
| T-004 | Reducer partial, dedup và ổn định turn | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-005 | Model session, migrations và memory store | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-006 | WebSocket ACK/outbox/recovery | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-007 | Bind tab và pause/resume/end | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-008 | Dashboard và navigation 5 màn hình | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-009 | Side panel live và card đang đọc | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-010 | Import repo/text/schema/export | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-011 | Ticket mapping và glossary | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-012 | Incremental index generation | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-013 | FTS5 retrieval cách ly project | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-014 | Semantic profile và hybrid search | IMPLEMENTED · E5 CPU thật + hybrid benchmark 10/10 top-5 trên corpus synthetic |
| T-015 | Citation registry, snapshot và source drawer | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-016 | Provider adapter và cấu hình key | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-017 | Prompt và validated suggestion | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-018 | Scheduler freshness, budget và cancellation | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-019 | Manual actions và snapshot card | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-020 | Report cấu trúc và evidence policy | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-021 | Long report, edit/version và conflict | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-022 | Lịch sử, tìm transcript và export | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-023 | Retention, delete và memory mode | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-024 | Metrics, cost estimate và lỗi vận hành | IMPLEMENTED · kiểm tra tự động tương ứng trong ACCEPTANCE_REPORT |
| T-025 | Windows setup/start/build và README chạy | IMPLEMENTED · PowerShell setup/build/start/health/Ctrl+C trên máy Windows hiện tại; máy sạch pending |
| T-026 | Meet thật: capture và recovery end-to-end | NOT TESTED · chưa có Meet thật hai participant; xem CAPTION_ADAPTER checklist |
| T-027 | Provider thật: kiểm tra nghĩa và báo cáo | PARTIAL · 6 mẫu ban đầu + 10 mẫu mở rộng; report synthetic 43 turns/2 map thật pass. Fault live/corpus thật/latency dài hạn còn chờ. Xem EXTENDED_LIVE_REPORT. |
| T-028 | Kiểm tra truy vết và bàn giao | IMPLEMENTED · registry/contract/evidence QA; release live gate còn mở |

Bổ sung response routing: IMPLEMENTED trong backend/UI, quy tắc local 5 luồng và API preview. Xem [RESPONSE_ROUTING.md](RESPONSE_ROUTING.md); chưa nghiệm thu Meet/provider thật cho luồng mới. [Ưu tiên tiếp theo](NEXT_PRIORITIES.md).
