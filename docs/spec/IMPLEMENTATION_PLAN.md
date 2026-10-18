# IMPLEMENTATION PLAN — Task cho Codex

Phiên bản: 1.1 · Ngày: 2026-10-11 · Trạng thái: tài liệu để triển khai, không phải báo cáo đã chạy ứng dụng.

Mọi task bên dưới hiện TODO. Dependency thể hiện thứ tự implementation; live evidence là gate riêng. Task checklist không thay thế acceptance.

[REQUIREMENTS.md](REQUIREMENTS.md) · [UI_UX_SPEC.md](UI_UX_SPEC.md) · [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md)

## 1. Cách dùng và trạng thái

- Codex đọc AGENTS.md, bộ spec và code hiện hữu; bắt đầu T-001, sau đó chọn task có dependency đã đủ.
- Task có title, REQ, check ID, module dự kiến và Done criteria. File paths là gợi ý cho workspace mới; repo hiện hữu có thể tương đương nếu ghi mapping.
- TODO → IN_PROGRESS → IMPLEMENTED → VERIFIED. BLOCKED chỉ cho phần thực sự bị môi trường/dữ liệu chặn.
- IMPLEMENTED nghĩa mã/build phù hợp; VERIFIED cần các check tương ứng có evidence. Không đổi task VERIFIED chỉ vì UI nhìn đẹp hoặc model tuyên bố thành công.
- Nếu T-003 thiếu Meet thật, tiếp tục reducer/backend/UI bằng interface và fixture có nhãn. Các phần cần DOM thật/live status vẫn BLOCKED hoặc NOT TESTED, không bịa selector. T-026 là nơi đóng gate live.
- Nếu thiếu key/model download/Windows, làm phần độc lập, ghi requirement/check còn pending. “Implementation ready for live validation” không đồng nghĩa MVP đã nghiệm thu.
- T-028 có thể xuất báo cáo có phần pending; phát hành “MVP VERIFIED” chỉ khi các gate bắt buộc thực sự pass.

## 2. Mốc và gate

| Phase | Kết quả | Gate |
| --- | --- | --- |
| A | Baseline + auth + capture adapter/reducer | Caption fixture pass; Meet experiment ghi đúng thực trạng |
| B | Session/transport và UI | ACK/dedup/recovery/state/pin không làm mất capture |
| C | Sources và retrieval | Project isolation, atomic sync, citations; keyword và semantic/fallback đúng |
| D | Text AI và manual controls | Schema/negation/uncertainty/freshness; provider test có nhãn thực/mock |
| E | Report/history/retention/Windows | Evidence/version/export, memory policy, operational behavior |
| F | Live validation và bàn giao | Meet thật + provider thật + Windows evidence, full acceptance report |

## 3. Task registry

| ID | Phase | Dependency | Task | REQ | Check | Status |
| --- | --- | --- | --- | --- | --- | --- |
| T-001 | A | — | Khởi tạo repo, dependency lock và baseline runtime | REQ-01, REQ-25, REQ-30 | OPS-02, DOC-01 | TODO |
| T-002 | A | T-001 | Pairing và loopback API/WS auth | REQ-23 | SEC-01, SEC-06 | TODO |
| T-003 | A | T-001 | Inspect Meet và adapter version đầu | REQ-02, REQ-04 | CAP-06, SCP-01 | TODO |
| T-004 | A | T-003 | Reducer partial, dedup và ổn định turn | REQ-03, REQ-04 | CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, TRN-02 | TODO |
| T-005 | B | T-001 | Model session, migrations và memory store | REQ-05, REQ-24 | SES-02, SEC-02 | TODO |
| T-006 | B | T-002, T-004, T-005 | WebSocket ACK/outbox/recovery | REQ-06, REQ-04 | TRN-01, TRN-02, TRN-03, TRN-04 | TODO |
| T-007 | B | T-005, T-006 | Bind tab và pause/resume/end | REQ-05, REQ-04 | SES-01, SES-02, TRN-04 | TODO |
| T-008 | B | T-002, T-005 | Dashboard và navigation 5 màn hình | REQ-18 | UX-01 | TODO |
| T-009 | B | T-007, T-008 | Side panel live và card đang đọc | REQ-16, REQ-18, REQ-04 | AI-06, UX-02, TRN-04, UX-01, CAP-05 | TODO |
| T-010 | C | T-005, T-008 | Import repo/text/schema/export | REQ-07, REQ-27, REQ-29 | SRC-01, SRC-02, SEC-04, SCP-01 | TODO |
| T-011 | C | T-010 | Ticket mapping và glossary | REQ-07, REQ-10 | SRC-01, RAG-05 | TODO |
| T-012 | C | T-010 | Incremental index generation | REQ-08 | RAG-02, RAG-03 | TODO |
| T-013 | C | T-011, T-012 | FTS5 retrieval cách ly project | REQ-09, REQ-10 | RAG-01, RAG-03, RAG-05 | TODO |
| T-014 | C | T-013 | Semantic profile và hybrid search | REQ-10 | RAG-05 | TODO |
| T-015 | C | T-013, T-008 | Citation registry, snapshot và source drawer | REQ-11 | CIT-01, AI-04 | TODO |
| T-016 | D | T-002, T-008 | Provider adapter và cấu hình key | REQ-23, REQ-28 | OPS-01, SEC-06 | TODO |
| T-017 | D | T-013, T-015, T-016 | Prompt và validated suggestion | REQ-12, REQ-13, REQ-14, REQ-29 | AI-01, AI-02, AI-03, AI-04, AI-07, AI-08, RAG-04 | TODO |
| T-018 | D | T-017, T-007 | Scheduler freshness, budget và cancellation | REQ-15, REQ-26, REQ-28 | AI-05, AI-09, OPS-03 | TODO |
| T-019 | D | T-009, T-018 | Manual actions và snapshot card | REQ-16, REQ-17 | UX-02, AI-06 | TODO |
| T-020 | E | T-017, T-007 | Report cấu trúc và evidence policy | REQ-19, REQ-20 | REP-03, AI-01, AI-02 | TODO |
| T-021 | E | T-020 | Long report, edit/version và conflict | REQ-21 | REP-01, REP-02 | TODO |
| T-022 | E | T-021, T-008 | Lịch sử, tìm transcript và export | REQ-22 | HIS-01 | TODO |
| T-023 | E | T-005, T-021, T-022 | Retention, delete và memory mode | REQ-24 | SEC-02, SEC-03, SEC-05 | TODO |
| T-024 | E | T-018, T-021 | Metrics, cost estimate và lỗi vận hành | REQ-26, REQ-28 | OPS-01, OPS-03 | TODO |
| T-025 | E | T-008, T-016, T-022 | Windows setup/start/build và README chạy | REQ-01, REQ-25 | OPS-02 | TODO |
| T-026 | F | T-009, T-019, T-025 | Meet thật: capture và recovery end-to-end | REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-18 | CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, CAP-06, TRN-03, TRN-04, SES-01, SES-02, UX-01, SCP-01 | TODO |
| T-027 | F | T-019, T-021, T-024 | Provider thật: kiểm tra nghĩa và báo cáo | REQ-12, REQ-13, REQ-14, REQ-19, REQ-20, REQ-21, REQ-28 | AI-01, AI-02, AI-03, AI-07, AI-08, REP-01, REP-02, REP-03, OPS-01 | TODO |
| T-028 | F | T-014, T-022, T-023, T-024, T-025 | Kiểm tra truy vết và bàn giao | REQ-30 | DOC-01, UX-01, HIS-01, OPS-02, OPS-03 | TODO |

## 4. Chi tiết task

### T-001 — Khởi tạo repo, dependency lock và baseline runtime

- Module dự kiến: extension/manifest, backend/app, scripts skeleton, lockfiles.
- Đáp ứng: REQ-01, REQ-25, REQ-30.
- Dependency: không; phase A.
- Done criteria: Các module build/import được; FTS5 capability check; README chỉ rõ bản chưa nối live.
- Verification: OPS-02, DOC-01 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-002 — Pairing và loopback API/WS auth

- Module dự kiến: backend auth/config; extension trusted storage.
- Đáp ứng: REQ-23.
- Dependency: T-001; phase A.
- Done criteria: REST/WS chặn token/origin/host sai; token riêng API key; key không gửi content script.
- Verification: SEC-01, SEC-06 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-003 — Inspect Meet và adapter version đầu

- Module dự kiến: extension/src/content/meet-adapter.ts; docs/CAPTION_ADAPTER.md.
- Đáp ứng: REQ-02, REQ-04.
- Dependency: T-001; phase A.
- Done criteria: Có adapter interface/diagnostics và selector dựa trên DOM đã quan sát; thử thật ghi evidence hoặc ghi live pending rõ.
- Verification: CAP-06, SCP-01 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-004 — Reducer partial, dedup và ổn định turn

- Module dự kiến: caption-reducer.ts; fixtures caption timelines.
- Đáp ứng: REQ-03, REQ-04.
- Dependency: T-003; phase A.
- Done criteria: Revision/speaker/epoch/seq đúng; silence khác loss; late correction giữ bản mới nhất.
- Verification: CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, TRN-02 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-005 — Model session, migrations và memory store

- Module dự kiến: backend storage/meetings, migrations.
- Đáp ứng: REQ-05, REQ-24.
- Dependency: T-001; phase B.
- Done criteria: Persistent hoặc RAM store đúng mode; transcript global revision; FK/migration/restart không phá dữ liệu.
- Verification: SES-02, SEC-02 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-006 — WebSocket ACK/outbox/recovery

- Module dự kiến: extension background transport; backend intake.
- Đáp ứng: REQ-06, REQ-04.
- Dependency: T-002, T-004, T-005; phase B.
- Done criteria: Retry idempotent; heartbeat, bounded queue, gap và worker restart có kiểm tra.
- Verification: TRN-01, TRN-02, TRN-03, TRN-04 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-007 — Bind tab và pause/resume/end

- Module dự kiến: backend session control; extension binding.
- Đáp ứng: REQ-05, REQ-04.
- Dependency: T-005, T-006; phase B.
- Done criteria: Project khóa; chỉ tab bound được intake; pause range; flush/end một lần; interrupted rõ.
- Verification: SES-01, SES-02, TRN-04 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-008 — Dashboard và navigation 5 màn hình

- Module dự kiến: extension/src/ui dashboard/routes/shared states.
- Đáp ứng: REQ-18.
- Dependency: T-002, T-005; phase B.
- Done criteria: 5 màn hình nối backend; empty/loading/error; quản lý không cần mở Meet.
- Verification: UX-01 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-009 — Side panel live và card đang đọc

- Module dự kiến: extension live panel reducer/view.
- Đáp ứng: REQ-16, REQ-18, REQ-04.
- Dependency: T-007, T-008; phase B.
- Done criteria: 320 px không cuộn ngang; capture/backend riêng trạng thái; pin không dừng intake; close/reopen giữ session.
- Verification: AI-06, UX-02, TRN-04, UX-01, CAP-05 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-010 — Import repo/text/schema/export

- Module dự kiến: backend ingestion; project UI.
- Đáp ứng: REQ-07, REQ-27, REQ-29.
- Dependency: T-005, T-008; phase C.
- Done criteria: Preview/path/root/limits/ignore đúng; schema không execute; metadata snapshot rõ.
- Verification: SRC-01, SRC-02, SEC-04, SCP-01 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-011 — Ticket mapping và glossary

- Module dự kiến: ingestion ticket parser; project glossary.
- Đáp ứng: REQ-07, REQ-10.
- Dependency: T-010; phase C.
- Done criteria: CSV/JSON field mapping, lỗi row có giải thích; ID/glossary được bảo toàn.
- Verification: SRC-01, RAG-05 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-012 — Incremental index generation

- Module dự kiến: backend indexing jobs/generation/hash.
- Đáp ứng: REQ-08.
- Dependency: T-010; phase C.
- Done criteria: Publish atomically; failed job giữ old good index; deleted/changed source cập nhật đúng.
- Verification: RAG-02, RAG-03 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-013 — FTS5 retrieval cách ly project

- Module dự kiến: backend retrieval FTS/query builder/cache.
- Đáp ứng: REQ-09, REQ-10.
- Dependency: T-011, T-012; phase C.
- Done criteria: Escape MATCH và SQL params; query/cache đúng project/generation; keyword baseline chạy không cần E5.
- Verification: RAG-01, RAG-03, RAG-05 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-014 — Semantic profile và hybrid search

- Module dự kiến: embedding model config/cache; settings model status.
- Đáp ứng: REQ-10.
- Dependency: T-013; phase C.
- Done criteria: E5 tokenizer/prefix/dim/revision chuẩn; fallback đúng nhãn; test EN/VI/ID và báo hit@5.
- Verification: RAG-05 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-015 — Citation registry, snapshot và source drawer

- Module dự kiến: backend request source snapshots; UI source drawer.
- Đáp ứng: REQ-11.
- Dependency: T-013, T-008; phase C.
- Done criteria: ID từ backend, excerpt/version/dòng rõ; source đổi/xóa không trỏ nhầm.
- Verification: CIT-01, AI-04 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-016 — Provider adapter và cấu hình key

- Module dự kiến: backend llm/client/credential/test endpoints; settings.
- Đáp ứng: REQ-23, REQ-28.
- Dependency: T-002, T-008; phase D.
- Done criteria: Key env/RAM; test connection thật khi có key; timeout/cancel/errors; mock có nhãn.
- Verification: OPS-01, SEC-06 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-017 — Prompt và validated suggestion

- Module dự kiến: llm prompts/schemas; source binding validation.
- Đáp ứng: REQ-12, REQ-13, REQ-14, REQ-29.
- Dependency: T-013, T-015, T-016; phase D.
- Done criteria: Reply VI/EN ngắn, không bịa; conflict/missing rõ; schema/citation valid trước ready.
- Verification: AI-01, AI-02, AI-03, AI-04, AI-07, AI-08, RAG-04 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-018 — Scheduler freshness, budget và cancellation

- Module dự kiến: backend suggestion scheduler; timing/usage.
- Đáp ứng: REQ-15, REQ-26, REQ-28.
- Dependency: T-017, T-007; phase D.
- Done criteria: Latest queued, revision/hash/generation binding; stale không overwrite; throttle/quota/cancel đúng.
- Verification: AI-05, AI-09, OPS-03 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-019 — Manual actions và snapshot card

- Module dự kiến: live controls; suggest actions API/UI.
- Đáp ứng: REQ-16, REQ-17.
- Dependency: T-009, T-018; phase D.
- Done criteria: Manual priority; shorten/explain/clarify dùng card snapshot; new badge; copy đúng kết quả.
- Verification: UX-02, AI-06 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-020 — Report cấu trúc và evidence policy

- Module dự kiến: backend reports schema/prompt; report UI.
- Đáp ứng: REQ-19, REQ-20.
- Dependency: T-017, T-007; phase E.
- Done criteria: Decision/action chỉ từ transcript; owner/due nullable, raw date/timezone; gap warning.
- Verification: REP-03, AI-01, AI-02 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-021 — Long report, edit/version và conflict

- Module dự kiến: reports chunk/merge/version; editor.
- Đáp ứng: REQ-21.
- Dependency: T-020; phase E.
- Done criteria: Không bỏ đuôi; preserve user edit; optimistic version check; conflict không silently overwrite.
- Verification: REP-01, REP-02 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-022 — Lịch sử, tìm transcript và export

- Module dự kiến: history/search/export backend; dashboard.
- Đáp ứng: REQ-22.
- Dependency: T-021, T-008; phase E.
- Done criteria: Filter đúng; export report version được chọn; giữ source/gap/cảnh báo trong export.
- Verification: HIS-01 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-023 — Retention, delete và memory mode

- Module dự kiến: storage cleanup/delete; settings/history UI.
- Đáp ứng: REQ-24.
- Dependency: T-005, T-021, T-022; phase E.
- Done criteria: Không ghi meeting payload khi memory mode; cascade/cache clean; sources giữ theo policy.
- Verification: SEC-02, SEC-03, SEC-05 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-024 — Metrics, cost estimate và lỗi vận hành

- Module dự kiến: usage/timing summaries; settings/errors.
- Đáp ứng: REQ-26, REQ-28.
- Dependency: T-018, T-021; phase E.
- Done criteria: Không bịa usage; price có date; report/capture timings; không log secret/transcript.
- Verification: OPS-01, OPS-03 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-025 — Windows setup/start/build và README chạy

- Module dự kiến: scripts/*.ps1; application README/config.
- Đáp ứng: REQ-01, REQ-25.
- Dependency: T-008, T-016, T-022; phase E.
- Done criteria: Setup/start/build usable; extension ID/pair instructions; demo/offline/real rõ.
- Verification: OPS-02 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-026 — Meet thật: capture và recovery end-to-end

- Module dự kiến: docs/CAPTION_ADAPTER.md; live evidence/report.
- Đáp ứng: REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-18.
- Dependency: T-009, T-019, T-025; phase F.
- Done criteria: Meet 2 participant; version/language; caption/panel/tab/disconnect cases; thiếu live ghi NOT TESTED.
- Verification: CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, CAP-06, TRN-03, TRN-04, SES-01, SES-02, UX-01, SCP-01 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-027 — Provider thật: kiểm tra nghĩa và báo cáo

- Module dự kiến: provider-live evidence; acceptance report.
- Đáp ứng: REQ-12, REQ-13, REQ-14, REQ-19, REQ-20, REQ-21, REQ-28.
- Dependency: T-019, T-021, T-024; phase F.
- Done criteria: So từng claim với source/transcript; không suy mock proof thành model proof; key thiếu ghi NOT TESTED.
- Verification: AI-01, AI-02, AI-03, AI-07, AI-08, REP-01, REP-02, REP-03, OPS-01 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

### T-028 — Kiểm tra truy vết và bàn giao

- Module dự kiến: docs/ACCEPTANCE_REPORT.md, LIMITATIONS.md; trace matrix.
- Đáp ứng: REQ-30.
- Dependency: T-014, T-022, T-023, T-024, T-025; phase F.
- Done criteria: PASS/FAIL/NOT TESTED có evidence; clean-start; known limitations; pending live của T-026/T-027 vẫn phải được ghi.
- Verification: DOC-01, UX-01, HIS-01, OPS-02, OPS-03 trong [ACCEPTANCE_SPEC.md](ACCEPTANCE_SPEC.md); lưu command/result/environment/evidence. Status ban đầu: TODO.

## 5. Quy trình làm một task

1. Nêu REQ/contract có thể ảnh hưởng; đọc module liên quan.
2. Implement một lát chạy được; không xây nhiều framework mới ngoài nhu cầu.
3. Kiểm tra hành vi quan trọng trong phạm vi thay đổi; update schema/types/docs khi thay contract.
4. Ghi kết quả thật. Test không chạy được có reason, không đổi sang PASS.
5. Kiểm tra integration dependency: dữ liệu/ID/revision giữa các module đúng.
6. Cập nhật task và acceptance report. Mô tả limitation cụ thể, tiếp tục task độc lập còn lại.

## 6. Handover artifacts của ứng dụng tương lai

Bộ spec hiện tại chưa chứa source ứng dụng. Codex khi triển khai phải tạo application README, lockfiles, migrations, scripts, fixtures và docs/CAPTION_ADAPTER.md, docs/ACCEPTANCE_REPORT.md, docs/LIMITATIONS.md.

Evidence cần phân biệt fixture/mock, Chrome extension thật, Meet thật, provider thật và Windows thật. Không ghi credential/transcript khách thật vào report công khai; dùng meeting thử và key sentinel trong security checks.

Bảng trace: [TRACEABILITY.md](TRACEABILITY.md). Schema và defaults: [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md).

