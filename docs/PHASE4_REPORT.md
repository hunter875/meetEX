# Phase 4 — bộ nhớ có evidence và báo cáo dài

**PARTIAL, 2026-10-19.** Đã triển khai và kiểm chứng phạm vi dưới đây; không chứng nhận ngữ nghĩa tổng quát hoặc MVP VERIFIED. Meet thật/model-quality evaluation thật: **NOT TESTED**. Paid provider calls mới: **0**.

## A–F

| Phần | Kết quả | Phạm vi và phần còn thiếu |
| --- | --- | --- |
| A. Memory có cấu trúc/evidence | PARTIAL | Schema/version/provenance/migration đã qua tests; automatic extraction chỉ grammar Anh rõ ràng. Requirement, proposal, decision, action, question, spoken fact phân biệt; project facts vẫn ở source retrieval, AI proposals tách riêng. |
| B. Thay đổi quyết định/nhận việc | PARTIAL | Explicit task/action/environment, same-speaker replacement/cancel, self-acceptance/take-over, conflict và correction qua corpus. Bare Yes chưa bind acceptance, kể cả antecedent có vẻ hợp lý; không có authority/coreference tổng quát. |
| C. Live context | PASS controlled | Memory đầu buổi ngoài cửa sổ gần, evidence nguyên turn, relevance/budget, memory revision trong hash/freshness, scope và guards. Chưa đo chất lượng gợi ý bằng model thật. |
| D. Report dài/xuyên maps | PARTIAL | 321 turns/16 maps: current/history, deadline mới/cancellation và validation qua pipeline; canonical summary chỉ bao phủ grammar đã nhận diện. Không bảo đảm completeness/entailment mọi câu hoặc họp nhiều giờ. |
| E. UI/chỉnh sửa/export | PASS automated | Trong Live/Report hiện có: state, owner/due, evidence đúng revision, lịch sử, optimistic edit/version, provenance, giữ report đã sửa khi regenerate; JSON/Markdown. |
| F. Đánh giá | PASS synthetic scope | 23 scenarios/38 labelled items, 5 held-out biến thể; field/evidence/relationship counts riêng, paired baseline và long pipeline. Không gọi fixture pass là accuracy thực tế. |

## Baseline và xác minh đầu vào

Branch đầu `codex/phase3-orchestration`, commit **`af868491a77a168e3ab68b457bb6a10c65f0c3f7`**, working tree sạch; không có AGENTS.md trong checkout/parent. Nhánh thực thi `codex/phase4-meeting-memory`. Đã đọc source storage, confirmed segments, snapshots/cache, report map/merge, validator/edit/export, retention/RAM và tài liệu Phase 1–3/requirements/contracts. Phase 3 vẫn PARTIAL; không đóng live gates cũ.

Baseline **276 backend / 58 frontend** qua: [JUnit](evidence/phase4/baseline-backend.xml), [frontend](evidence/phase4/baseline-frontend.json). Trước sửa chỉ có confirmed transcript segments do người dùng chọn, không có structured ledger, state transitions hoặc revision archive độc lập. Report nối map summaries/dedup text+evidence, không đối chiếu trạng thái cuối.

[Schema/quy tắc viết trước triển khai](PHASE4_DESIGN.md), [corpus labels](../fixtures/phase4/meeting-memory.json) và [script tạo corpus](../scripts/build_phase4_corpus.py). Label item/state/owner/due có trước engine; assertions về graph edges được thêm sau bản grammar đầu, nên **không coi graph score là held-out độc lập**. Baseline đối chiếu dùng frozen source archive từ commit trên, chạy cùng harness sau khi fixture được cố định; không checkout đè worktree.

## Ví dụ trước → sau

| Tình huống | Trước | Sau trong grammar hỗ trợ |
| --- | --- | --- |
| Deploy Friday → confirmed Monday instead → cancel | Hai quyết định có thể cùng nằm phần confirmed sau merge | Friday superseded, Monday cancelled, cancellation hiện hành; mở được evidence/lịch sử từng bước |
| Minh nhận review API-17, khách hỏi API-18 | Chưa có structured owner history | API-17 accepted/Minh; API-18 requested, owner null; không gán chéo |
| Staging test confirmed; production deploy pending | Report guard có giới hạn, chưa có ledger state | Hai mệnh đề/scope riêng: staging confirmed, production unconfirmed |
| Caption “approved production” sửa thành “NOT approved production” | Bỏ confirmed-segment thủ công và stale card, thiếu item history | Cùng item ID, version mới unconfirmed; revision 1 lưu nguyên, cache/card liên quan stale |
| “I will review … by tomorrow” | ReportItem chỉ giữ raw relative date | Ledger chuẩn hóa theo ngày của evidence trong timezone phiên; report legacy field vẫn raw, ledger export chứa ngày/rule/anchor |
| Bạn đổi owner thành Alex | Có report user edit/version | Memory edit thêm origin/provenance/version; không được phát biểu như participant Alex đã nhận; regenerate giữ riêng user-edited ledger snapshot |

Bare “Yes” được giữ như phát biểu, không tự xác nhận request/owner. “We have not approved it” không bịa đối tượng: ghi unconfirmed và đánh dấu các decision sát trước có thể liên quan là disputed/cần làm rõ, không tự hủy một task bất kỳ.

## Data model, state và evidence

Migration **002**, chạy theo `schema_version` một lần trong transaction; 001 cũ không chạy lại trên DB đã nâng cấp. Không reset DB. Ba bảng mới ở đúng SQLite local/RAM:

- `segment_revisions`: `(meeting_id, segment_id, revision)` → raw payload, gồm speaker/text/stable/time. Correction không xóa revision cũ.
- `memory_items`: scoped meeting/project, ID ổn định, latest version/payload.
- `memory_versions`: immutable payload mỗi version, FK vào item/meeting, cascade khi xóa/retention.

Item có kind, nguyên mệnh đề, entity/entities, action/environment, speaker, owner/candidate_owner, state/event_state, raw_due_text/normalized_due/due_rule/due_anchor, origin, evidence refs, relations, order và policy `meeting-ledger-v1`. ID transcript là hash meeting/segment/clause slot; correction cùng slot giữ ID và lịch sử version, không khẳng định nội dung hai version giống nhau. User-created note dùng UUID và origin `user_edit`. Annotation giữ `transcript_basis` nguyên dữ liệu trước sửa; engine reconcile speech trước rồi overlay annotation. Không xóa quan hệ superseded chỉ vì successor được user sửa. Khi caption sửa evidence của annotation, giữ annotation invalidated và tạo speech lineage riêng có ID ổn định sau fork; không âm thầm ghi đè bản user hoặc bỏ qua correction.

| Kind | States có hành vi |
| --- | --- |
| requirement | requested, withdrawn (withdrawn hiện qua user edit) |
| proposal | proposed, accepted, rejected (rejected hiện qua user edit) |
| decision | unconfirmed, confirmed, disputed, superseded, cancelled |
| action_item | requested, accepted, completed, disputed, superseded, cancelled |
| open_question | open, resolved (resolved hiện qua user edit) |
| spoken_fact | stated; là participant phát biểu, chưa xác minh độc lập |
| mọi kind | invalidated khi evidence revision bị mất hiệu lực |

Không dùng một enum status chung để cho phép mọi state cho mọi kind; PATCH kiểm tra state theo kind. Project facts có source/generation/citation riêng trong retrieval, không tự thành meeting acceptance/deployment. AI proposal vẫn là `ai_proposals` của report, không thành lời participant hoặc tự nhập vào ledger. Nguồn model confidence không tham gia xác nhận.

Reconcile theo **exact task ID/action/environment**. Proposal mới không thay confirmed. Explicit correction/change/instead từ cùng speaker có thể supersede; explicit self negative/cancel chỉ hủy đúng task liên quan. Cross-speaker contradictions được giữ disputed, không mặc định người mới nhất có authority. Take-over cần chính người mới nhận và nêu `from` owner cũ. Named third-party “will” chỉ là request/candidate, không acceptance. Quote/reported/conditional được giữ stated/proposed; không lấy việc nhận A để nhận B.

`current(item)` loại invalidated/superseded/rejected/withdrawn và các node đã liên kết accepted_by/cancelled_by/completed_by/superseded_by. Cancellation tombstone mới vẫn hiện; bản confirmed cũ có cancelled_by chỉ ở lịch sử. Quan hệ chỉ có ID trong cùng meeting, mỗi đầu quan hệ mở được revision evidence riêng.

Caption partial không extraction; nếu revision/speaker sửa evidence đã dùng thì invalidate ngay, stable mới parse lại. Reconcile lại các item cùng meeting từ raw events, giữ user edits và mọi versions. Item có nhiều evidence refs cũng invalidate nếu một ref đổi (có test dependency riêng; grammar hiện phần lớn tạo atomic single-clause items). Legacy data không tự nâng verified; `memory-rebuild` chủ động chỉ đọc current stable captions, không bịa revisions đã mất.

Deadline chỉ lấy trong context task/decision/proposal có action; ngày của incident/fact không thành due. Giữ raw. ISO hợp lệ hoặc `tomorrow` dùng **observed timestamp của evidence**, chuyển timezone meeting, cộng một ngày local. Maybe/conditional/next Friday/early next week không chuẩn hóa thành deadline chắc chắn. Overdue không đổi accepted thành completed/failed. Thứ trong tuần chỉ raw/ambiguous. ReportItem cũ vẫn giữ quy tắc normalized_due chặt của Phase 1; normalized relative date có trong ledger snapshot/export, không nới validator cũ.

## Cadence, live context và resource policy

Extraction/reconciliation local synchronous trong transaction caption sau accepted revision, không model extraction cho stable/partial. Không đổi heartbeat/reconnect thành model trigger. `memory_update` metric chỉ lưu duration float, tối đa 1.000 samples; không persist transcript qua telemetry. ACK gửi sau transaction, nên full caption-apply đo cả overhead memory.

Live chọn tối đa **8 items / 2.000 ký tự JSON** theo exact entity + lexical relevance, bao gồm disputed/unconfirmed/cancellation còn liên quan. Original evidence nguyên turn dùng chung budget memory **8 turns/3.000 ký tự** với legacy confirmed segments; không đủ budget thì bỏ nguyên item, tăng omitted count. Tổng snapshot budget 18.000 ký tự như trước; không cắt nửa câu. `memory_revision` vào snapshot/cache/preparation identity/freshness; source/index version vẫn độc lập. Pin/action trên card giữ immutable snapshot cũ với cảnh báo stale khi cần.

Memory revision có thể khiến thêm generation stale, kể cả revision cosmetic trên turn đã tạo ledger; đây là lựa chọn bảo thủ hơn ngoại lệ Phase 3 để không dùng sai evidence version. [Replay Phase 3 hiện tại](evidence/phase4/orchestration-regression.json) vẫn 39/39 attempted, 0 missed/false trigger, 40 logical/42 HTTP; wire user JSON **27.197 → 28.931 ký tự (+6,38%)**. Không gọi đó là tiết kiệm token; real usage unknown.

Legacy confirmed segments đã bị ledger hủy/thay thế/disputed không còn dùng làm current memory; relevance xét cả context gần/legacy evidence. Live guard kiểm tra cả lời hứa bỏ task ID và alias Anh–Việt, bổ sung chặn positive claim trái cancelled/disputed/unconfirmed và buộc ghi chú `user_edit` được quy nguồn rõ, không giả participant speech. Guard schema/role/evidence/negation/task/numeric Phase 1 vẫn chạy. Memory/source text là untrusted DATA, không system instruction. Named-owner reply được đối chiếu với đúng speaker/task acceptance; alias “tôi sẽ” vẫn đi qua self-commitment guard, không bị nhầm là tên người.

Cache retrieval giữ query digest, không caption nguyên văn làm key. Forget/deletion/retention xóa query/vector caches và tăng epoch: worker cũ không repopulate cache sau xóa. CPU worker đã chạy có thể hoàn tất read transaction rồi bỏ kết quả; không force-kill thread, không ghi query vào disk. Background jobs bounded theo cơ chế hiện có, cancelled trước publish; RAM DB và cache đóng/mất khi restart. Source deletion không biến historical excerpts thành current sources.

## Report reconciliation và chỉnh sửa

Map/repair vẫn validate bằng guard cũ. Tối đa **64 maps**, mỗi map deadline tổng **90 s** mặc định, bao gồm retry/repair; tối đa 2 generation passes × 2 HTTP attempts = **4 attempts/map**, không thêm lượt tổng hợp LLM. Vượt capacity lỗi rõ, không cắt transcript rồi coi đủ. Combined map summaries vượt 15.000 ký tự hoặc một memory clause vượt 4.000 ký tự/report item cũng lỗi capacity rõ, giữ transcript và bản cũ; không âm thầm cắt rồi phát ready. Tổng worst case vẫn lớn; budget toàn job/queue hardening dành Phase 5.

Sau map merge, `report_ledger.reconcile_report` liên kết bằng task/evidence. Governed model paraphrases được giữ trong historical/map draft; phần current được dựng lại từ exact ledger clauses còn hiệu lực. Owner/due gán sang task khác bị từ chối. User-edited memory nằm riêng trong `memory_snapshot` có origin, không tái chứng nhận thành participant action. Map items ngoài grammar vẫn qua validator Phase 1; chưa chứng minh mọi claim đúng.

Summary của phạm vi có ledger stateful được dựng deterministic từ states còn hiệu lực, không nối các confirmation cũ. Phần chưa rõ hỏi làm rõ; bản VI hiển thị trạng thái/câu hỏi, positive evidence giữ nguyên lời tiếng Anh có nhãn nguyên văn. Không giả là bản dịch model hoàn chỉnh. Summary map gốc chỉ ở lịch sử/draft; không là evidence mới. Các mục/summary current và historical được validate chung để giữ coverage lời nhận việc cũ, rồi kiểm tra current state riêng; không bỏ guard coverage để xóa lời đã nói. Capture gaps/unknown scope và cảnh báo thiếu dữ liệu vẫn xuất trong report.

Report lưu immutable `memory_snapshot`, `memory_revision`, `evidence_snapshot`, `historical_payload`, reconciliation metadata. Caption/memory thay đổi sau đó chỉ làm response hiện `evidence_changed`, không sửa payload report cũ. Evidence drawer của report dùng bản lưu tương ứng; legacy không có archive hiển thị chưa thể chứng nhận revision history.

Memory PATCH dùng expected_version; note/edit luôn origin `user_edit`, actor/changed fields/previous version. Report PATCH giữ expected_version/parent/version, item origin và summary edit provenance. User sửa/thêm proposal cũng mang origin user_edit; model giả origin này vẫn bị chặn. AI-proposal bucket vẫn cấm confirmed owner/deadline, kể cả sau user edit. Regenerate tạo version mới, giữ saved edits; UI không cho regenerate khi draft chưa lưu. JSON/Markdown có current/history, owner/due, origin, revision refs/relations và warnings. App không gửi báo cáo hay cập nhật connector.

## Đánh giá có nhãn

Máy Windows 11 build 26200, Ryzen 7 5800H, 8 cores/16 logical CPUs, Python 3.13.4, Node 22.20.0; cùng locks hiện có. Không thêm dependency/service. UTC timestamps trong evidence; ngày báo cáo theo context người dùng America/Los_Angeles (lượt làm việc đi qua 18→19/10).

Corpus: **23 synthetic scenarios**, 18 tuning / 5 held-out biến thể, 5 loại họp refinement/progress/QA-release/incident/technical. Bao phủ proposal, confirmed, replaced/cancelled, owner take-over, conflict, hai task/owner/due, staging/production, conditional/quote, NOT correction, timezone tomorrow, gap, injection, project scope, user edit và long pipeline. Held-out cùng tác giả/grammar family, không là đánh giá độc lập thực tế.

SHA256 UTF-8/LF corpus: `662192bf32ca0bf2c61236afb85046af3d5c24fa11f7b9fb431956d90177ae6e`. Harness/config/hash/source manifest trong [review](evidence/phase4/review.json). [Baseline](evidence/phase4/evaluation-baseline.json) không có structured ledger: 38 expected items chưa có biểu diễn, không gọi đó là 0% accuracy model. [After](evidence/phase4/evaluation-after.json):

| Chỉ số / mẫu số | Actual |
| --- | --- |
| Items đúng / expected | **38/38** |
| Sai / bỏ sót / extra trong nhãn | **0 / 0 / 0** |
| Tuning / held-out items đúng | **29/29 / 9/9** |
| Owner non-null đúng / expected | **11/11**, sai 0; false owner ở các item còn lại 0 |
| Normalized due đúng / expected | **6/6**, sai 0; false normalized due ở các item còn lại 0 |
| Confirmed decision hoặc accepted/completed action đúng | **14/14**, false confirmation ở 24 items còn lại 0 |
| Evidence binding theo item đúng | **38/38**; một turn có thể support nhiều item |
| Supersede/cancel/conflict/completion/accept edges | **12/12**, thiếu/extra 0; supplemental edge assertions, không held-out độc lập |

Không cộng owner null/date null thành accuracy owner/deadline. Gold item/state labels nhỏ và explicit, không đo semantic extraction của model thật. Ambiguous multi-entity clause chưa tách được giữ một unresolved raw item có entities, không đoán owner/action cho mỗi entity. Bài multi-task split có hai mệnh đề đã kiểm tra riêng. Bare Yes chưa được tính thành accepted gold item.

Long controlled pipeline riêng: **321 turns, 16 maps**, decision đầu buổi, owner ở giữa, deadline cuối, cancellation sau đó. Cả hai bản chạy actual Provider SSE adapter với MockTransport, delay cố định 5 ms, không model thật:

| Long pipeline | Baseline → Phase 4 |
| --- | --- |
| Confirmed decisions hết hiệu lực còn current | **2 → 0** |
| Deadline cũ còn current | **1 → 0** |
| Summary nêu cancellation cuối | không → có |
| Summary positive trái final trong phép dò giới hạn | 0 → 0; baseline summary neutral nhưng thiếu final state |
| HTTP attempts / retry / repair | **16/0/0 → 16/0/0** |
| Report wall latency | **645,88 → 703,77 ms** (+57,89 ms, +8,96%) |
| Full caption apply median / p95 / max (n=321) | **0,129 / 0,247 / 0,712 → 0,821 / 0,920 / 1,042 ms** |
| Memory engine update median / p95 / max (n=321) | chưa có → **0,632 / 0,686 / 0,857 ms** |
| Usage known / unknown attempts | **0/16 → 0/16** |
| Real tokens / real cost | **unknown / unknown**, không mặc định cancelled miễn phí |

Phép đo cùng máy chạy sequential, RAM meeting, samples nhỏ/corpus synthetic; không phải disk I/O SLA, speech-to-UI hoặc latency model thật. ACK concurrency khi semantic worker bị giữ vẫn có regression test; không suy rằng indexing lớn/full RAM/RSS mọi cấu hình đã nghiệm thu. Test report HTTP thật qua MockTransport riêng tạo **503 → retry → validation repair**, đếm đúng **3 attempts / 1 retry / 1 repair / 3 unknown usage**. Per-job attempt counters không phụ thuộc buffer provider metrics 2.000 records.

## Regression và lỗi đã xử lý

**331 backend / 60 frontend / 6 browser E2E pass**, build/typecheck/OpenAPI contracts/docs QA pass. [Backend](evidence/phase4/backend-final.xml), [frontend](evidence/phase4/frontend-final.json), [browser](evidence/phase4/browser-final-results.json), [semantic](evidence/phase4/semantic-regression.json): 82 fixtures và 3 original probes vẫn bị chặn. Một Starlette/anyio deprecation warning cũ. [Verification](evidence/phase4/verification.json) ghi commands/status; [UI memory](evidence/phase4/browser-final/phase4-memory-ui.png), [report](evidence/phase4/browser-final/phase4-report-ui.png).

Các file first/candidate/focused giữ thất bại trước sửa: response DTO defaults khác raw export; harness evidence index cho hai clause/cùng turn; UI label/select và chọn self trước khi quan sát; summary metadata thiếu scope hoặc dùng câu phủ định không được guard hỗ trợ. Đã sửa source/harness/wording và retest, **không nới model-output/evidence guards hay giảm assertion Phase 1–3 (riêng user-edit proposal origin được sửa đúng provenance, vẫn cấm confirmed owner/deadline)**. Summary không đủ căn cứ dùng câu hỏi làm rõ. Test fixture TypeScript chỉ thêm defaults DTO, không đổi assertions cũ. Báo cáo/evidence/spec Phase 1–3 giữ nguyên.

## File/hàm chính

- [meeting_memory.py](../backend/app/meeting_memory.py): extract/reconcile/update/save_versions/edit/select/current/check_live_claims.
- [002.sql](../backend/app/migrations/002.sql), [storage.py](../backend/app/storage.py): versioned migration, archive revisions, memory transaction, cascade/report view.
- [service.py](../backend/app/service.py): live evidence budget/version/cache/freshness; bounded map/reconcile/report snapshot/edit provenance/job counts.
- [report_ledger.py](../backend/app/report_ledger.py), [llm.py](../backend/app/llm.py): deterministic cross-map current/history, original validation, provider correlation/attempt counts.
- [main.py](../backend/app/main.py), [models.py](../backend/app/models.py): scoped memory/evidence/history/edit/rebuild API, metrics/export/contracts.
- [retrieval.py](../backend/app/retrieval.py): digest query key/epoch eviction, không repopulate sau xóa.
- [memory.tsx](../extension/src/ui/memory.tsx), [live.tsx](../extension/src/ui/live.tsx), [report.tsx](../extension/src/ui/report.tsx): UI trong màn hình hiện có, immutable evidence, edit/version/export.

## Tái tạo

Từ root sau setup; không cần provider key. `build_phase4_corpus.py` ghi lại labels cố định, không dùng output model để sinh gold.

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q --junitxml=docs/evidence/phase4/backend-final.xml
node node_modules/vitest/vitest.mjs run --root extension --reporter=json --outputFile=../docs/evidence/phase4/frontend-final.json
.\.venv\Scripts\python.exe scripts/export_openapi.py
npm run typecheck
npm run build
npm run contracts
$env:MEET_E2E_EVIDENCE_DIR='docs/evidence/phase4/browser-final'
$env:MEET_E2E_RESULTS_FILE='docs/evidence/phase4/browser-final-results.json'
node node_modules/@playwright/test/cli.js test
.\.venv\Scripts\python.exe scripts/evaluate_phase1.py --output docs/evidence/phase4/semantic-regression.json --base-commit af868491a77a168e3ab68b457bb6a10c65f0c3f7 --starting-branch codex/phase3-orchestration
.\.venv\Scripts\python.exe scripts/benchmark_phase3.py --output docs/evidence/phase4/orchestration-regression.json
```

Paired source archive/harness (cùng máy, sequential khi idle):

```powershell
New-Item -ItemType Directory -Force .local/phase4-baseline | Out-Null
git archive --format=zip --output=.local/phase4-baseline/source.zip af868491a77a168e3ab68b457bb6a10c65f0c3f7 backend
.\.venv\Scripts\python.exe -c "import zipfile; zipfile.ZipFile('.local/phase4-baseline/source.zip').extractall('.local/phase4-baseline')"
$env:MEET_PHASE4_BACKEND=(Resolve-Path .local/phase4-baseline/backend).Path
.\.venv\Scripts\python.exe scripts/evaluate_phase4.py --output docs/evidence/phase4/evaluation-baseline.json
Remove-Item Env:MEET_PHASE4_BACKEND
.\.venv\Scripts\python.exe scripts/evaluate_phase4.py --output docs/evidence/phase4/evaluation-after.json
.\.venv\Scripts\python.exe scripts/review_phase4.py
.\.venv\Scripts\python.exe scripts/documentation.py
.\.venv\Scripts\python.exe scripts/check_docs.py
```

Audit exit 0 nghĩa checks chạy và evidence khớp; **không đổi overall PARTIAL thành PASS**. Hash source/harness chuẩn UTF-8/LF để tái tạo sau clone. Các artifacts synthetic có raw example transcript là test output chủ động, không product telemetry persist RAM meetings.

## Dạng sai còn có thể lọt và Phase 5

Grammar explicit Anh/task ID/action/environment chưa có paraphrase, multilingual/tiếng Việt có dấu, authorization hierarchy, entity resolution hoặc coreference tổng quát. Bare Yes không tự nhận việc; unbound denial có thể gây disputed bảo thủ. Cùng action/task nhưng hai subtask không được phân biệt bằng ID/scope có thể cần người dùng chỉnh; mệnh đề compound chưa tách chắc giữ unresolved, không đoán relations. Fact được phát biểu chưa là fact đúng; chưa phát hiện mọi mâu thuẫn factual/source. Named third party và participant labels không xác minh danh tính/authority. Same-speaker sửa rõ mới được tự replace; người khác hủy có thể chưa đủ căn cứ. Relative dates ngoài ISO/tomorrow giữ raw; không tự diễn giải next Friday. Cửa sổ/budget/relevance có thể bỏ item quan trọng ngoài grammar; report cảnh báo phạm vi, không hứa đầy đủ.

Live guards dùng alias/keyword có giới hạn, chưa liên kết được mọi phủ định/qualifier trong compound reply và có thể chặn nhầm câu nhắc lịch sử. Model paraphrases ngoài ledger vẫn có thể sai qualitative entailment hoặc bị Phase 1 guard chặn nhầm; report có evidence IDs không chứng minh claim đúng. Long transcript là synthetic 321 turns, không nghiệm thu họp hàng giờ/capture thật. RAM mode đã kiểm tra DB/files/caches/cascade, không tuyên bố chống OS swap/process dump. CPU worker không force-preempt. Worst-case 64 maps × 90 s/job, nhiều report background/legacy revisions/rất nhiều items cần operational hardening; memory reconcile hiện quét ledger cùng meeting, không graph database.

Phase 5: CI đầy đủ và migrations upgrade/rollback/fault injection; refactor module/DTO/current-history presentation; setup/update/backup/retention hardening; report toàn-job budget/cumulative usage durable và concurrency limits; đo full RSS/indexing/ACK trên corpus thật; Meet hai participant/Windows sạch/restart/outage nghiệm thu theo [runbook](PHASE2_LIVE_RUNBOOK.md). Model-quality thật chỉ chạy khi có authorization + budget mới. Không có connector sống, tự gửi report/update ticket, bot execution, cross-project memory, training hoặc multiuser trong Phase 4.
