# Tài liệu Meet Copilot

Snapshot trong [hunter875/meetEX](https://github.com/hunter875/meetEX), GitHub báo public khi kiểm tra 2026-10-18. Ứng dụng chạy local; chưa nghiệm thu Google Meet thật. Thư mục spec giữ nguyên tài liệu đầu vào, không dùng trạng thái TODO trong đó thay cho kết quả triển khai hiện tại.

## Bắt đầu và kiến trúc

- [Cài đặt, pairing extension, chạy và xử lý lỗi](../README.md)
- [Thiết kế kỹ thuật ban đầu](spec/TECHNICAL_DESIGN.md) và [kiến trúc/API bộ nhớ hiện tại](MEETING_MEMORY.md)
- [Các quyết định và thay đổi contract khi triển khai](CONTRACT_CHANGES.md)
- [OpenAPI hiện tại](openapi.json) và [TypeScript sinh từ schema](../extension/src/api-schema.d.ts)
- [Adapter caption và checklist Meet thật](CAPTION_ADAPTER.md)

## Trạng thái và kiểm tra

- [Trạng thái triển khai](IMPLEMENTATION_STATUS.md), [truy vết yêu cầu](TRACEABILITY.md), [báo cáo nghiệm thu](ACCEPTANCE_REPORT.md).
- Phase 4: **331 backend / 60 frontend / 6 browser pass**. [A–F, PARTIAL và phạm vi](PHASE4_REPORT.md), [review](evidence/phase4/review.json): 38/38 labelled items/evidence, 321-turn/16-map controlled report; model/Meet thật NOT TESTED.
- Phase 3 lịch sử: **276 backend tests, 58 frontend unit tests, 5 browser E2E pass**. [Báo cáo A–F, PARTIAL theo mục tiêu đặt trước](PHASE3_REPORT.md), [review/source hashes](evidence/phase3/review.json). 39/39 eligible attempted, false trigger 7 → 0, logical 49 → 40; hai mục tiêu request/Auto wait chưa đạt. Zero paid calls mới, Meet/provider thật mới NOT TESTED.
- Phase 2 lịch sử: [capture/recovery A–G](PHASE2_REPORT.md), [review](evidence/phase2/review.json), [runbook live](PHASE2_LIVE_RUNBOOK.md). Các regression đã chạy lại trong Phase 3 với MV3/backend thật, DOM synthetic/provider intercepted.
- [Response routing](RESPONSE_ROUTING.md): local rules-v1, 5 luồng, preview/lý do, chọn mode thủ công, gate xác minh; [34/34 fixture](evidence/routing-review.json) là phạm vi synthetic, không phải accuracy tổng quát.
- [Đánh giá hệ thống](SYSTEM_ASSESSMENT.md), [giới hạn](LIMITATIONS.md), [các chức năng ưu tiên tiếp theo](NEXT_PRIORITIES.md).

## Bằng chứng provider và tốc độ

- [6 kịch bản ban đầu](LIVE_PROVIDER_REPORT.md), [10 kịch bản mở rộng](EXTENDED_LIVE_REPORT.md): provider thật, lời thoại mô phỏng. Không cộng các bộ có lặp case thành số mẫu độc lập.
- [Latency trước routing](LATENCY_REPORT.md): median 1,498 s trên 10 mẫu tương ứng, 1,520 s trên 16 mẫu; warm backend, không phải speech-to-UI hay SLA. Chưa đo lại provider thật theo luồng sau khi thêm routing.
- [Transcript mô phỏng 8 lượt](evidence/transcript-meeting-demo.md), [transcript dài 43 lượt](evidence/transcript-long-demo.md).
- `docs/evidence/` giữ cả các lần lỗi trước sửa và retest. Các file cũ là lịch sử, không phải mọi file đều là PASS của build hiện tại. Report review chỉ rõ lần nào được dùng.

## Các phần chưa hoàn thành

Meet thật/Windows sạch/outage thực tế chưa nghiệm thu. Ba probe gốc đã bị chặn trong phạm vi giai đoạn 1; guard vẫn chưa xác minh mọi claim. Routing không thay bộ kiểm tra bằng chứng. Luồng deep mới dùng prompt trong schema gợi ý, chưa có bảng phương án/trọng số. Chưa có bộ nhớ quyết định có trạng thái thay thế/hủy, connector đồng bộ sống hoặc PDF/DOCX trực tiếp.

## Đưa lên Git và tái tạo tài liệu

Repository chứa source, dependency locks, schema, tests, fixtures và bằng chứng mô phỏng. Không chứa `.env`, API key, pairing token, SQLite/cuộc họp local, `.local/models`, `.venv`, node_modules hay bản build extension. Sau clone chạy setup/build, tạo pairing và đặt key riêng; không dùng token trong test làm token thật. Không tự gán license khi chủ sở hữu chưa chọn.

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_routing.py
.\.venv\Scripts\python.exe scripts\review_phase4.py
.\.venv\Scripts\python.exe scripts\documentation.py
.\.venv\Scripts\python.exe scripts\check_docs.py
npm run contracts
```

Chạy từ gốc repository sau setup. Quy trình test đầy đủ ở README. `documentation.py` dựng lại trạng thái/nghiệm thu từ evidence; không chạy lại provider trả phí. Hash routing được chuẩn hóa UTF-8/LF để kiểm tra được sau clone trên các hệ điều hành.

## Kết quả giai đoạn 1

[Báo cáo A–E và phạm vi giới hạn](PHASE1_REPORT.md) · [Semantic review mới](evidence/phase1/semantic-review.json) · [Backend 219 tests](evidence/phase1/backend-final.xml) · [Browser E2E mới](evidence/phase1/browser-final-results.json). Baseline 91 tests và các lần lỗi trước sửa được giữ riêng trong evidence/phase1.
