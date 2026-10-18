# Phase 3 — điều phối AI, latency, chi phí và giảm trùng

**PARTIAL, 2026-10-18.** Các cải thiện dưới đây đã được kiểm chứng offline; hai mục tiêu đặt trước chưa đạt. Không có paid provider call mới. Meet thật và benchmark provider thật của build Phase 3: **NOT TESTED**. Không gọi đây là MVP VERIFIED.

## A–F và quyết định triển khai

| Phần | Kết quả | Thay đổi và giới hạn |
| --- | --- | --- |
| A. Trigger theo nội dung | PARTIAL | `content-trigger-v1`: câu hỏi ngắn 150 ms, thông tin/correction 800 ms, batch không quá 2 s khi scheduler rảnh. Không gọi model để phân loại caption. Đủ nhãn replay nhưng không bảo đảm câu gián tiếp/tiếng Việt có dấu/code-switching; Auto chờ manual vượt mục tiêu 500 ms. |
| B. Scheduler/manual | PASS automated | Một live generation active, một latest queued; manual ưu tiên cả preparation và provider, Auto không thay manual. Same-context inflight coalesces, cancel không ready; pause/end/interrupted/delete dọn pending. PASS giới hạn các tests hiện tại. |
| C. Request/card dedup | PARTIAL | Hash đủ scope/source generation/mode/provider configuration/policy; narrow card dedup chỉ exact payload + cùng semantic context. Giữ câu hỏi mới/hỏi lại và thay đổi số/NOT/owner/deadline/environment/ID. Replay không có duplicate-card cần bỏ (0 → 0); unit tests chứng minh nhánh duplicate, chưa chứng minh giảm lặp chủ đề thực tế. |
| D. Context/retrieval | PASS measured scope | Giữ nguyên turn, focus và tiền đề gần; budget rõ, dedup excerpt giống hệt; async RO SQLite transaction, cache và vectorization. Top-5 không giảm trong fixture, ACK vẫn qua khi worker bị giữ. Cold keyword chậm hơn; chỉ đo Python allocation peak, chưa full RSS/repo thật lớn. |
| E. Provider | PARTIAL | Giữ model/pooling/keepalive/validator; timeout tổng gồm retry/repair; correlation và đếm HTTP đầy đủ. Không biết token/cost/model latency thật của build mới. |
| F. Metrics/benchmark/UI | PASS controlled | Replay có nhãn, baseline đối chiếu, buffer giới hạn và trạng thái chờ/xử lý/nghe/quota/stale. UI không đưa debug policy vào luồng bình thường. Render notification là tín hiệu message/rAF, chưa phải speech-to-pixel. |

Chọn cấu hình này vì bỏ false trigger và giảm context mà vẫn xử lý mọi nhãn bắt buộc; không kéo dài debounce hoặc loại câu hỏi để đạt số request đẹp hơn. Khi manual chậm, giữ ưu tiên manual và một generation active. Đây là trade-off có chủ đích, không đổi mục tiêu sau tuning.

## Baseline, tài liệu tham khảo và môi trường

Đầu vào: branch `codex/phase2-capture`, commit `bccc6f5bbb94711ae71e13c654b65dfe687940c3`, working tree sạch, không có AGENTS.md trong checkout/parent. Nhánh triển khai `codex/phase3-orchestration`. Đã đọc source và báo cáo Phase 1–2, chạy baseline 228 backend / 56 frontend; baseline evidence giữ riêng trong [phase3](evidence/phase3/). Không mặc định live gate đã đóng.

Tham khảo bản được đọc:

- [tfp24601/live-meeting-assistant](https://github.com/tfp24601/live-meeting-assistant/tree/47d518101023300b1a8feeaaa7f56a3c69cd53c6), commit `47d518101023300b1a8feeaaa7f56a3c69cd53c6`, MIT: suggestions engine/retrieval/LLM dispatcher và cadence/context. Học cách gắn cadence với lượng nội dung; không lấy mặc định 12 s/120 ký tự làm ngưỡng meetEX. Không nhập logic cứu output sai schema/cắt output của repo tham khảo.
- [krystiangw/meet-live-assist-extension](https://github.com/krystiangw/meet-live-assist-extension/tree/c26b04e6eb875a44536bed5afb3e80ce49b56ff1), commit `c26b04e6eb875a44536bed5afb3e80ce49b56ff1`, **PolyForm Internal Use 1.0.0**: transcript buffer/wake gating/cut trong server. Không sao chép source; license có giới hạn phân phối, không coi là MIT.

Máy cùng checkout: Windows 11 build 26200 x64, AMD Ryzen 7 5800H, 8 cores/16 logical CPUs, Python 3.13.4, Node 22.20.0. Locks hiện có; không thêm service/dependency mặc định. E5 optional dùng `intfloat/multilingual-e5-small`, revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, CPU. Ngày báo cáo theo context người dùng, timezone America/Los_Angeles; artifact lưu timestamp UTC riêng.

[Replay chính](../fixtures/phase3/orchestration-replay.json) có **31 scenario: 27 tuning, 4 held-out biến thể**, tổng **39 eligible events**. SHA256 UTF-8/LF: `fd7ca8d79c779b42182cd517534c3f51c047042fb6db143fd378eb8730bdb895`. Expected labels và [targets.json](evidence/phase3/targets.json) được tạo trước sửa policy; không sửa ngưỡng sau khi thấy kết quả. Held-out nhỏ, cùng tác giả/rule family, không phải đánh giá độc lập trên cuộc họp thật.

Nhóm gồm small talk, partial dài, câu ngắn/dài, participant khác/self/unknown speaker, let-finish, cosmetic/NOT/số/owner/deadline/environment correction, hỏi lại, hai câu hỏi nhanh, đổi chủ đề, nguồn mâu thuẫn/generation đổi, provider chậm/lỗi/retry/repair và pause/end/reconnect. [Replay pin/manual bổ sung](../fixtures/phase3/ui-lifecycle-replay.json) được thêm sau tuning, **không nhập vào mẫu số mục tiêu gốc**: cả hai bản 3 logical/3 attempts; action dùng đúng held snapshot. E2E còn kiểm tra pin/badge thật trong extension.

Harness chạy production Service + Provider + validator với SSE `MockTransport`, clock ảo bước 25 ms, delay provider bình thường 300 ms/chậm 3.000 ms; input 18.000 ký tự, output budget 800 tokens. Hai bản dùng cùng corpus/harness/config và synchronous keyword wrapper cho riêng phép đo scheduler; retrieval async đo bằng wall clock riêng. Không đưa timing thread không xác định vào clock ảo. Model output controlled chỉ là câu hỏi trung lập, không phải model trả lời thực tế.

## Kết quả đối chiếu và mục tiêu giữ nguyên

Nguồn: [baseline](evidence/phase3/orchestration-baseline.json), [sau tối ưu](evidence/phase3/orchestration-after.json), [review có hash source/harness](evidence/phase3/review.json).

| Chỉ số trên 31 scenario | Baseline | Phase 3 |
| --- | ---: | ---: |
| Eligible events | 39 | 39 |
| Eligible có attempted generation | 37/39 | 39/39 |
| Missed theo nhãn | 2/39 | 0/39 |
| False Auto trigger | 7 | 0 |
| Logical requests (bỏ skipped) | 49 | 40 |
| Provider HTTP attempts | 51 | 42 |
| Transient retry / validation repair attempts | 1 / 1 | 1 / 1 |
| Ready / stale / error / cancelled requests | 43 / 2 / 1 / 3 | 35 / 2 / 1 / 2 |
| Skipped / superseded | 5 / 0 | 0 / 0 |
| Cards lưu / ready publication proxy | 45 / 43 | 37 / 35 |
| Exact duplicate cards cùng context | 0 | 0 |
| Tổng user JSON ký tự gửi qua mọi attempt | 32.384 | 27.197 |
| Attempts usage known / unknown | 0 / 51 | 0 / 42 |
| Tokens thật / cost thật | unknown | unknown |

`processed` là **attempted scoped generation**, bao gồm cả cancelled/stale/error; không có nghĩa trả lời thành công. `ready` chỉ là publication proxy sau validator, **không phải card hữu ích do người dùng chấm**. Số ready ít hơn vì giảm gọi thừa; không dùng tỷ lệ này để khẳng định chất lượng model. Quota vẫn đếm logical; HTTP attempt count cho thấy retry/repair có chi phí riêng. Cancelled không được mặc định miễn phí; missing usage giữ unknown. Ước lượng input ký tự/3 có nhãn estimate, không phải tokenizer hoặc usage.

| Tập | Eligible attempted trước → sau | Miss trước → sau | False trước → sau | Logical trước → sau | HTTP trước → sau |
| --- | --- | --- | --- | --- | --- |
| Tuning 27 scenarios | 32/33 → 33/33 | 1 → 0 | 5 → 0 | 42 → 35 | 44 → 37 |
| Held-out 4 scenarios | 5/6 → 6/6 | 1 → 0 | 2 → 0 | 7 → 5 | 7 → 5 |

| Mục tiêu đặt trước | Actual | Kết quả |
| --- | --- | --- |
| Mandatory missed = 0 | 0/39 | PASS fixture |
| False trigger giảm ≥50% | 7 → 0, giảm 100% trên 7 false ban đầu | PASS fixture |
| Logical requests giảm ≥20% | (49−40)/49 = **18,37%** | **NOT MET** |
| Mọi câu ngắn schedule wait ≤500 ms | Idle 150 ms; slow-manual Auto **2.900 ms** | **NOT MET** |
| Continuous batch đầu ≤2.000 ms | 2.000 ms clock ảo; 9 stable revisions → 2 generations | PASS fixture |
| Context fixture giảm ≥20% wire chars | 5.538 → 1.872, **66,20%** | PASS fixture |
| Live generation active tối đa 1 | 1, JUnit property | PASS tests |

Tổng wire chars giảm 16,02% trên mọi attempt; con số 66,20% chỉ thuộc `context-budget`, không áp cho toàn corpus. Trường `wire_chars` đo user JSON được serialize, không gồm system prompt/transport bytes/token usage. Latency mỗi route và từng event được giữ trong hai JSON, bao gồm error/cancel/stale; không chỉ lọc ready. Provider normal/slow là delay điều khiển, không chứng minh fast 1–2 s hoặc deep 5–10 s thật.

## Context, retrieval và trade-off

Snapshot giữ 8 turn gần nhất, toàn bộ focus đang chờ (tối đa 32), tối đa 3 turn tiền đề cho câu tham chiếu, confirmed memory hiện có tối đa 8 đoạn/3.000 ký tự và budget JSON 18.000 ký tự. Turn/excerpt được giữ hoặc bỏ nguyên khối, có omitted counts; không cắt nửa câu thành fact. Focus nhiều câu hỏi được đưa vào prompt/routing, lời cảm ơn sau cùng không chiếm focus. Không gửi toàn repository hoặc gọi model tóm tắt trên mỗi caption. Vượt capacity trả lỗi rõ, không giả vờ xử lý đủ.

Retrieval dùng executor 1 worker, tối đa 8 inflight distinct, coalesce cùng key; SQLite connection RO riêng trong worker với read transaction bao trùm metadata/chunks, không chia sẻ connection chính. Query LRU 128 entries; vector matrices tối đa 2 generation/project sets; buffers timing tối đa 1.000. Cache xét scope/glossary/generation/stale/semantic state; RAM only. Tính dot product float32 vectorized, parse vector thẳng vào native memory, không dựng danh sách hàng triệu Python floats.

[Retrieval baseline](evidence/phase3/retrieval-baseline.json) → [after](evidence/phase3/retrieval-after.json). Mỗi size/mode **12 queries = 3 query IDs lặp 4 lần**; baseline 0 cache hit, after 9/12. Cold là lần đầu; warm n=11 gồm cả 9 cache hit. Uncached sau n=3, trước n=12, nên phải đọc cold và warm cùng nhau.

| Chunks / mode | Cold ms trước → sau | Warm median / p95 ms trước → sau | Uncached median ms trước → sau |
| --- | --- | --- | --- |
| 100 keyword | 8,12 → 62,75 | 4,84 / 6,11 → 1,00 / 8,87 | 4,86 → 8,87 |
| 100 hybrid vectors | 110,18 → 46,63 | 100,51 / 144,50 → 0,92 / 9,60 | 102,25 → 9,60 |
| 1.000 keyword | 36,71 → 44,14 | 35,71 / 39,24 → 0,97 / 22,52 | 35,78 → 22,52 |
| 1.000 hybrid vectors | 1.383,57 → 298,77 | 922,78 / 1.215,23 → 0,88 / 35,87 | 927,32 → 35,87 |
| 10.000 keyword | 168,32 → 218,30 | 160,55 / 164,99 → 1,05 / 232,28 | 160,72 → 218,30 |
| 10.000 hybrid vectors | 8.369,53 → 2.490,17 | 9.598,47 / 10.286,32 → 1,00 / 252,00 | 9.377,74 → 252,00 |

Mọi hàng giữ **12/12 top-5**, 0 scope violation. Corpus 100/1.000/10.000 có SQL text/chunks synthetic và **orthogonal vectors điều khiển**, không phải semantic recall trên 10.000 đoạn văn thật. Cold keyword 10k chậm hơn 29,7% do dispatch/connection/copy overhead; đổi lại event-loop max tick 160,83 → 17,16 ms. Hybrid 10k max tick 1.716,76 → 21,31 ms, Python peak 26.759.457 → 23.645.944 bytes. Peak là `tracemalloc`, **không gồm native NumPy/model/full process RSS**; không tuyên bố tổng RAM giảm tương ứng. Tick samples ít, không phải ACK SLA.

Test WebSocket riêng giữ semantic worker chưa hoàn thành rồi gửi caption: ACK vẫn về dưới 500 ms; test đồng thời source publish bảo đảm kết quả dùng cùng metadata/chunks generation, lượt sau thấy generation mới. Không suy ra indexing lớn luôn không chặn writer/API.

**E5 CPU thật chỉ trên demo 12 chunks/10 queries:** top-5 10/10 → 10/10; median 45,75 → 36,11 ms, p95/max **52,95 → 68,97 ms (xấu hơn)**. Model load 22,98 → 22,15 s; OS/download/model caches có thể ảnh hưởng, không gán thay đổi load cho thuật toán. Không có billing cho embedding local; đây không phải provider generation thật.

## Freshness, cancellation và pin

Guard evidence/schema/role/scope của Phase 1 giữ nguyên; mọi generation/repair/fast/deep vẫn validate trước publish. Timeout live là deadline tổng cho generation + transient retry + một validation repair. ContextVar liên kết logical ID/automatic/generation attempt/HTTP reason; key/caption không vào telemetry. Full snapshot/provenance giữ riêng khỏi prompt compact.

Freshness nới **rất hẹp**: chỉ cho output của immutable snapshot tiếp tục nếu log revision liên tục đủ chứng minh các segment gốc chỉ đổi casing/dấu câu không đổi meaning key và speaker, hoặc append turn mới chỉ là lời chào/cảm ơn nhận diện được. Bare Yes/No được xử lý như thay đổi quan trọng; OK/ack khác có thể bỏ trigger nhưng vẫn làm kết quả đang chạy stale, không suy đó là lời xã giao an toàn. Revision payload giữ nguyên, timing có `cosmetic_or_new_smalltalk_only`; không đổi nhãn stale để hợp thức hóa sai đáp án. Boundary punctuation chuẩn hóa, nhưng dấu trong số/domain/path/task ID và unit có phân biệt được giữ. Thiếu log, substantive append, NOT/số/owner/deadline/environment/source/context/provider/self đổi vẫn stale. Log revision tối đa 128; fallback bảo thủ. Memory correction hiện có vẫn hủy xác nhận theo contract cũ.

Manual mới hủy preparation cũ hoặc generation cũ; task cancelled không phát ready ngay cả provider nuốt cancel. Auto mới không thay pending manual; các focus độc lập được gộp, không có backlog một request mỗi caption. Partial/let-finish dừng timer batch tới khi lượt ổn định phù hợp; own speech bỏ pending Auto. Pause/end và trạng thái không active không tạo generation. Quota chỉ chặn Auto, không chặn manual hợp lệ.

Reducer bỏ offer đến muộn hơn current/pending theo created_at; explicit manual action vẫn có thể dùng card cũ người dùng chọn. Pin giữ nguyên card, gợi ý mới vào badge, shorter/explain/clarify giữ snapshot đang chọn. Các hành vi được kiểm tra bằng unit/integration và 5 E2E dùng Chromium MV3/backend thật, DOM synthetic/provider intercepted.

## Regression và bằng chứng cuối

Source chính: [orchestration.py](../backend/app/orchestration.py) (`decide`, `meaning_key`, `card_key`, `retrieval_query`); [service.py](../backend/app/service.py) (`prepare_async`, `schedule_async`, `arm_auto`, `run_live`, `equivalent_changes_only`); [retrieval.py](../backend/app/retrieval.py) (`search_async`, `search`); [llm.py](../backend/app/llm.py) (`live_context`, provider attempt metrics). [Reducer](../extension/src/ui/card-reducer.ts), [Live UI](../extension/src/ui/live.tsx), [models](../backend/app/models.py) và [API](../backend/app/main.py) cập nhật contract/state tương ứng.

- [276 backend tests](evidence/phase3/backend-final.xml), 0 fail; một Starlette/anyio deprecation warning hiện có.
- [58 frontend tests](evidence/phase3/frontend-final.json), typecheck/build/OpenAPI contracts pass.
- [5 browser E2E](evidence/phase3/browser-final-results.json), gồm capture/recovery Phase 2, pin, quota, scheduler trạng thái. [UI synthetic snapshot](evidence/phase3/browser-final/phase3-ui.json) và screenshot là artifact test chủ động, không phải product tự persist RAM transcript.
- [82 semantic fixtures và 3 probe gốc](evidence/phase3/semantic-regression.json) pass trong grammar/alias Phase 1; không chứng minh entailment tổng quát.
- [Review mục tiêu/source hashes](evidence/phase3/review.json), [documentation QA](evidence/phase3/documentation-qa.json), [verification commands](evidence/phase3/verification.json). Phase 1–2 reports/evidence không bị ghi đè. Các file `first`, `candidate`, `metric-v1`, `native-first` giữ thử nghiệm trước sửa; không dùng chúng làm kết quả cuối.

Hai test cũ dùng request giống hệt để kỳ vọng cancel/supersede được đổi input thành request khác; thêm assertion cùng input trả cùng request ID. Các assertion cancellation/quota/latest-wins cũ vẫn giữ. Fixture frontend chỉ bổ sung field DTO mới; không giảm kiểm tra capture/semantic.

## Tái tạo

Sau setup backend/extension (semantic lock chỉ cần cho E5), chạy từ root. Không cần API key. Các test dùng sentinel giả và MockTransport, không gọi external provider.

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q --junitxml=docs/evidence/phase3/backend-final.xml
node node_modules/vitest/vitest.mjs run --root extension --reporter=json --outputFile=../docs/evidence/phase3/frontend-final.json
.\.venv\Scripts\python.exe scripts/export_openapi.py
npm run typecheck
npm run build
npm run contracts
$env:MEET_E2E_EVIDENCE_DIR='docs/evidence/phase3/browser-final'
$env:MEET_E2E_RESULTS_FILE='docs/evidence/phase3/browser-final-results.json'
node node_modules/@playwright/test/cli.js test
.\.venv\Scripts\python.exe scripts/evaluate_phase1.py --output docs/evidence/phase3/semantic-regression.json --base-commit bccc6f5bbb94711ae71e13c654b65dfe687940c3 --starting-branch codex/phase2-capture
```

Tạo frozen baseline archive (không checkout đè worktree), rồi chạy cùng harness:

```powershell
New-Item -ItemType Directory -Force .local/phase3-baseline | Out-Null
git archive --format=zip --output=.local/phase3-baseline/source.zip bccc6f5bbb94711ae71e13c654b65dfe687940c3 backend
.\.venv\Scripts\python.exe -c "import zipfile; zipfile.ZipFile('.local/phase3-baseline/source.zip').extractall('.local/phase3-baseline')"
$env:MEET_BENCH_BACKEND=(Resolve-Path .local/phase3-baseline/backend).Path
.\.venv\Scripts\python.exe scripts/benchmark_phase3.py --output docs/evidence/phase3/orchestration-baseline.json
.\.venv\Scripts\python.exe scripts/benchmark_phase3.py --fixture fixtures/phase3/ui-lifecycle-replay.json --output docs/evidence/phase3/lifecycle-baseline.json
Remove-Item Env:MEET_BENCH_BACKEND
.\.venv\Scripts\python.exe scripts/benchmark_phase3.py --output docs/evidence/phase3/orchestration-after.json
.\.venv\Scripts\python.exe scripts/benchmark_phase3.py --fixture fixtures/phase3/ui-lifecycle-replay.json --output docs/evidence/phase3/lifecycle-after.json
```

Retrieval script imports backend directly; preload baseline module for old run. Run sequentially on idle machine; `--real-e5` loads pinned optional local model (may download model cache, no paid provider). Omit flag for controlled vectors only.

```powershell
.\.venv\Scripts\python.exe -c "import runpy,sys; sys.path.insert(0,r'D:\meetEX\.local\phase3-baseline\backend'); import app.retrieval; sys.argv=['scripts/benchmark_phase3_retrieval.py','--output','docs/evidence/phase3/retrieval-baseline.json','--real-e5']; runpy.run_path('scripts/benchmark_phase3_retrieval.py',run_name='__main__')"
.\.venv\Scripts\python.exe scripts/benchmark_phase3_retrieval.py --output docs/evidence/phase3/retrieval-after.json --real-e5
.\.venv\Scripts\python.exe scripts/evaluate_phase3.py
.\.venv\Scripts\python.exe scripts/documentation.py
.\.venv\Scripts\python.exe scripts/check_docs.py
```

Thay `D:\meetEX` bằng đường dẫn clone nếu cần. `review.json` ghi source/harness hashes chuẩn UTF-8/LF. `evaluate_phase3` giữ PARTIAL khi hai mục tiêu chưa đạt; exit 0 của evaluator nghĩa audit chạy thành công, không có nghĩa mọi mục tiêu đạt. Retrieval timing mẫu nhỏ sẽ biến động giữa các run.

## Giới hạn và Phase 4

Rule có thể miss câu hỏi gián tiếp/không dấu hỏi/tiếng Việt mới hoặc gọi thừa ở correction mang tính trình bày. Stable không phải final; không dùng audio để nhận turn-end. Narrow normalization không chứng minh đồng nghĩa; card dedup chưa xử lý paraphrase/topic. Batch tối đa 32 focus, retrieval wait tối đa 10 s (không quá live deadline), context/token/model quality vẫn là giới hạn hữu hạn. Caption bỏ ngoài cửa sổ/memory có thể thiếu tiền đề dài; source recall giữ trên fixture không bảo đảm repo thật. Không có weighted decision matrix, decision memory dài hạn, connector sống, STT/TTS, execution agent hay multiuser/multiworker mới.

Phase 4 cần: đóng Meet live gate theo [runbook](PHASE2_LIVE_RUNBOOK.md); thu corpus được phép dùng và chấm câu hỏi/card hữu ích, false reject/accept/scope theo người; benchmark provider thật với authorization + budget mới, cold/warm/error/cancel usage đầy đủ; mở rộng semantic corpus và đo full RSS/index writer; hiệu chỉnh indirect questions/multilingual và giảm duplicate paraphrase có bằng chứng. Weighted options cần tiêu chí/trọng số do người dùng xác nhận và kiểm tra độ nhạy, không bịa confidence. Hai mục tiêu chưa đạt vẫn mở, không tự giảm threshold nghiệm thu.
