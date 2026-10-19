> Hiện hành: [Phase 5 / release gates](PHASE5_REPORT.md). Ma trận bên dưới là snapshot Phase 4 và truy vết spec gốc, không phải nghiệm thu Phase 5.

# REQ → task → check

Bảng dựng lại từ registry trong sáu tệp được cung cấp; không thay đổi spec gốc. Kết quả được tách theo mode trong [ACCEPTANCE_REPORT.md](ACCEPTANCE_REPORT.md).

| REQ | Ưu tiên / yêu cầu | Tasks | Checks |
| --- | --- | --- | --- |
| REQ-01 | P0 · Chạy local trên Windows/Chrome | T-001, T-025 | DOC-01, OPS-02 |
| REQ-02 | P0 · Dùng phụ đề Meet | T-003, T-026 | CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, CAP-06, SCP-01, SES-01, SES-02, TRN-03, TRN-04, UX-01 |
| REQ-03 | P0 · Caption không trùng/sai revision | T-004, T-026 | CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, CAP-06, SCP-01, SES-01, SES-02, TRN-02, TRN-03, TRN-04, UX-01 |
| REQ-04 | P0 · Trạng thái và khoảng thiếu | T-003, T-004, T-006, T-007, T-009, T-026 | AI-06, CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, CAP-06, SCP-01, SES-01, SES-02, TRN-01, TRN-02, TRN-03, TRN-04, UX-01, UX-02 |
| REQ-05 | P0 · Phiên đúng tab/project | T-005, T-007, T-026 | CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, CAP-06, SCP-01, SEC-02, SES-01, SES-02, TRN-03, TRN-04, UX-01 |
| REQ-06 | P0 · Phục hồi transport | T-006, T-026 | CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, CAP-06, SCP-01, SES-01, SES-02, TRN-01, TRN-02, TRN-03, TRN-04, UX-01 |
| REQ-07 | P0 · Nhập dữ liệu dự án | T-010, T-011 | RAG-05, SCP-01, SEC-04, SRC-01, SRC-02 |
| REQ-08 | P0 · Đồng bộ đúng phiên bản | T-012 | RAG-02, RAG-03 |
| REQ-09 | P0 · Cách ly dự án | T-013 | RAG-01, RAG-03, RAG-05 |
| REQ-10 | P1 · Tìm kiếm keyword và semantic | T-011, T-013, T-014 | RAG-01, RAG-03, RAG-05, SRC-01 |
| REQ-11 | P0 · Nguồn kiểm tra được | T-015 | AI-04, CIT-01 |
| REQ-12 | P0 · Gợi ý dễ hiểu, dễ nói | T-017, T-027 | AI-01, AI-02, AI-03, AI-04, AI-07, AI-08, OPS-01, RAG-04, REP-01, REP-02, REP-03 |
| REQ-13 | P0 · Không bịa hoặc tự cam kết | T-017, T-027 | AI-01, AI-02, AI-03, AI-04, AI-07, AI-08, OPS-01, RAG-04, REP-01, REP-02, REP-03 |
| REQ-14 | P0 · Output AI được validate | T-017, T-027 | AI-01, AI-02, AI-03, AI-04, AI-07, AI-08, OPS-01, RAG-04, REP-01, REP-02, REP-03 |
| REQ-15 | P0 · Gợi ý mới và chi phí có kiểm soát | T-018 | AI-05, AI-09, OPS-03 |
| REQ-16 | P0 · Giữ câu đang đọc | T-009, T-019 | AI-06, CAP-05, TRN-04, UX-01, UX-02 |
| REQ-17 | P0 · Điều khiển AI thủ công | T-019 | AI-06, UX-02 |
| REQ-18 | P0 · Đủ năm màn hình | T-008, T-009, T-026 | AI-06, CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, CAP-06, SCP-01, SES-01, SES-02, TRN-03, TRN-04, UX-01, UX-02 |
| REQ-19 | P0 · Báo cáo có bằng chứng | T-020, T-027 | AI-01, AI-02, AI-03, AI-07, AI-08, OPS-01, REP-01, REP-02, REP-03 |
| REQ-20 | P0 · Owner/date có xác nhận | T-020, T-027 | AI-01, AI-02, AI-03, AI-07, AI-08, OPS-01, REP-01, REP-02, REP-03 |
| REQ-21 | P0 · Báo cáo dài và phiên bản | T-021, T-027 | AI-01, AI-02, AI-03, AI-07, AI-08, OPS-01, REP-01, REP-02, REP-03 |
| REQ-22 | P1 · Lịch sử và xuất | T-022 | HIS-01 |
| REQ-23 | P0 · Key và pairing đúng chỗ | T-002, T-016 | OPS-01, SEC-01, SEC-06 |
| REQ-24 | P0 · Lưu/xóa có policy | T-005, T-023 | SEC-02, SEC-03, SEC-05, SES-02 |
| REQ-25 | P0 · Khởi động và demo rõ ràng | T-001, T-025 | DOC-01, OPS-02 |
| REQ-26 | P1 · Đo thời gian và usage thật | T-018, T-024 | AI-05, AI-09, OPS-01, OPS-03 |
| REQ-27 | P0 · DB là snapshot trong MVP | T-010 | SCP-01, SEC-04, SRC-01, SRC-02 |
| REQ-28 | P0 · Provider lỗi/timeout/cancel rõ | T-016, T-018, T-024, T-027 | AI-01, AI-02, AI-03, AI-05, AI-07, AI-08, AI-09, OPS-01, OPS-03, REP-01, REP-02, REP-03, SEC-06 |
| REQ-29 | P0 · Nguồn và nội dung không chạy lệnh | T-010, T-017 | AI-01, AI-02, AI-03, AI-04, AI-07, AI-08, RAG-04, SCP-01, SEC-04, SRC-01, SRC-02 |
| REQ-30 | P0 · Bàn giao truy vết và bằng chứng | T-001, T-028 | DOC-01, HIS-01, OPS-02, OPS-03, UX-01 |
