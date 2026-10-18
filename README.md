# Meet Copilot · Local

Trợ lý dành cho developer Việt Nam họp với khách nói tiếng Anh: đọc **phụ đề Google Meet**, truy xuất nguồn dự án local, gợi ý câu tiếng Anh A2–B1, giải thích tiếng Việt và soạn báo cáo có bằng chứng.

Repository: [hunter875/meetEX](https://github.com/hunter875/meetEX) (GitHub báo public khi kiểm tra 2026-10-18). [Mục lục tài liệu và trạng thái hiện tại](docs/README.md).

Snapshot Phase 3: **276 backend tests, 58 frontend tests, 5 browser E2E pass**. [Báo cáo A–F](docs/PHASE3_REPORT.md): **PARTIAL** theo mục tiêu đặt trước; replay 39/39 eligible attempted, false trigger 7 → 0, logical requests 49 → 40 (giảm 18,37%, chưa đạt 20%). Auto ưu tiên manual nên wait có thể 2,9 s; không cam kết 1,5 s đầu cuối. [Phase 2 capture/recovery](docs/PHASE2_REPORT.md) được regression lại; [Meet thật còn NOT TESTED](docs/PHASE2_LIVE_RUNBOOK.md). Không có paid provider call mới. Bộ phân loại local 34/34 fixture Anh–Việt chưa phải accuracy họp thật; bảng phương án trọng số còn trong [danh sách ưu tiên](docs/NEXT_PRIORITIES.md).

Có năm màn hình: **Dự án & dữ liệu, Đang họp, Báo cáo, Lịch sử, Cài đặt**. Chrome MV3 + React/TypeScript/Vite; FastAPI một worker; SQLite WAL/FTS5; E5 CPU tùy chọn. Không cần Docker/GPU. Không thu audio, tự nói, gửi chat/email, chạy source/SQL hoặc kết nối production DB.

Trạng thái triển khai và kết quả chạy thực tế ở [docs/ACCEPTANCE_REPORT.md](docs/ACCEPTANCE_REPORT.md). [DeepSeek thật đã chạy 6 tình huống synthetic và 2 reports](docs/LIVE_PROVIDER_REPORT.md), có transcript/gợi ý/bằng chứng. Chưa có profile DOM Meet được xác nhận qua phiên hai participant; lần đầu cần chọn vùng phụ đề đang hiển thị. Fixture DOM không thay kiểm tra Meet thật.

Đã thử thêm [10 kịch bản mở rộng và 6 báo cáo](docs/EXTENDED_LIVE_REPORT.md): đổi deadline/owner, CSV/JSON/schema, injection trong tài liệu, cách ly project và transcript 43 turns qua hai map. Hai lỗi lượt đầu được sửa và có targeted retest; evidence trước sửa vẫn giữ nguyên.

[Latency provider lịch sử trước routing/Phase 1–3](docs/LATENCY_REPORT.md): cùng 10 mẫu, median giảm 2,67 → 1,50 s; 16 mẫu cuối median 1,52 s, max 3,40 s. Phase 3 đo scheduler controlled và retrieval riêng; chưa đo lại provider thật. Mọi output vẫn validate trước khi hiện.

## Chạy trên Windows

Đã dùng Windows 11, Node **22.20.0**, npm **10.9.3**, Python **3.13.4**, SQLite có FTS5. Cần Node 22.12+ và official Python 3.11+ có `python` trong PATH. `tzdata` được cài để IANA timezone chạy trên Windows.

Mở PowerShell tại thư mục dự án:

Nếu lấy từ GitHub lần đầu, clone:

```powershell
git clone https://github.com/hunter875/meetEX.git
cd meetEX
```

Chạy các script dưới từ thư mục clone. `D:\meetEX` là đường dẫn trên máy phát triển, có thể thay bằng đường dẫn của bạn:

```powershell
cd D:\meetEX
.\scripts\setup.ps1
.\scripts\build-extension.ps1
.\scripts\start-backend.ps1
```

Nếu chính sách PowerShell chặn script, chạy đúng script local bằng `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1`; các script còn lại tương tự. Không cần thay policy toàn máy. Setup dùng `npm ci` và dependency lock; không thực thi repository khách.

Backend nghe **127.0.0.1:8765**, một Uvicorn worker. Dừng bằng **Ctrl+C** để hủy job và đánh dấu phiên bị gián đoạn. Dữ liệu ở `.local/` mặc định; đổi bằng `MEET_DATA_DIR` trong environment hoặc `.env`. API key không được ghi vào thư mục này.

### Nạp và pair extension

1. Mở [Chrome Extensions](chrome://extensions), bật Developer mode, chọn **Load unpacked** → `D:\meetEX\extension\dist`.
2. Copy ID extension, chạy ở PowerShell khác:

   ```powershell
   .\scripts\pair-extension.ps1 -ExtensionId YOUR_32_CHARACTER_EXTENSION_ID
   ```

3. Dừng/khởi động lại backend. Script chỉ lưu Origin extension trong `.env`.
4. Mở **Details → Extension options** để vào dashboard. Trong **Cài đặt**, nhập backend URL `http://127.0.0.1:8765` và pairing token đọc bằng:

   ```powershell
   Get-Content .\.local\pairing-token
   ```

5. Bấm **Lưu kết nối**. Pairing token là credential local riêng, không phải DeepSeek API key. Extension ID phải khớp allowlist backend. Không mở backend ra LAN.

Manifest giới hạn content script trên `https://meet.google.com/*`; quyền `sidePanel`, `storage`, `alarms`. Quyền alarms phục hồi kết nối worker. Backend request chạy trong extension context. Storage token/profile chỉ mở cho trusted extension contexts; outbox và card chỉ dùng `chrome.storage.session` RAM.

### Thử luồng không cần API key

Giữ backend đang chạy, mở PowerShell khác:

```powershell
.\scripts\load-demo.ps1
```

Chọn project **DEMO · Customer Portal** trong **Đang họp**, bật **Chế độ demo có nhãn**, Start. Thêm phụ đề thử rồi **Tạo gợi ý**. Demo dùng câu hỏi làm rõ có kiểm soát; không phải bản dịch hay suy luận model thật. Thử giữ card, kết thúc, tạo báo cáo, chỉnh sửa, lưu phiên bản, xuất Markdown/JSON. Muốn thử auto, cần transcript có tên của bạn và người khác rồi chọn “Tôi”.

### Dùng trong Meet

1. Tạo project; thêm repo local/text/Markdown/SQL schema hoặc CSV/JSON. **Xem trước** để kiểm tra file/row bị bỏ qua; **Nhập & tạo index**. SQL được đọc như văn bản. Repo, ticket, schema và CSV đều là snapshot; không chứng minh trạng thái production.
2. Trong tab Meet được phép thử, bật phụ đề tiếng Anh. Nhấn biểu tượng extension để mở **side panel**.
3. Lần đầu hoặc khi DOM thay đổi: **Chọn vùng phụ đề Meet / Chọn DOM**. Chọn vùng chứa caption blocks → xác nhận; chọn đúng chữ của một câu → xác nhận; chọn speaker cùng block hoặc bỏ qua. Không chọn chat/toàn trang. Profile được tạo từ DOM bạn vừa chọn, không phải selector chính thức của Google.
4. Chọn project, tên phiên, local/RAM rồi Start. Project khóa theo phiên; worker bind tab/document/meeting path. Đoạn đang render lúc bắt đầu/resume được bỏ qua để không backfill; đợi lượt nói mới. Kiểm tra nguyên văn và trạng thái capture trước khi dựa vào gợi ý.
5. Chọn participant **Tôi** khi có tên. Chưa xác định speaker thì dùng thủ công; ứng dụng không tự gọi người mới nói là khách. “Stable” sau khoảng 1 giây là heuristic; sửa muộn vẫn cập nhật revision.
6. **Giữ câu** khóa card, không dừng capture. Gợi ý mới vào hàng chờ; bấm **Có gợi ý mới** để chuyển. Ngắn hơn/Giải thích/Hỏi lại dùng snapshot card đang hiển thị.
7. Pause không lưu nội dung mới; Resume không thu bù. End flush/đợi ACK tối đa 2 giây; thiếu ACK ghi cảnh báo. Đóng panel không kết thúc phiên. Tab đóng/đổi meeting hoặc backend restart làm phiên interrupted; tiếp tục chủ động tại đúng tab.
8. End → mở báo cáo → tạo nháp → mở evidence, sửa, lưu phiên bản, xem lại và copy/xuất. Không tự gửi báo cáo. Regenerate giữ bản người dùng đã sửa. Owner/deadline chưa rõ hiển thị “Chưa xác nhận”.

## Provider thật

Trong **Cài đặt**, nhập API key bằng ô password và **Đặt key vào RAM**. Key mất sau restart backend. Hoặc cấp environment `DEEPSEEK_API_KEY` từ môi trường riêng của bạn; không đưa key vào source, browser storage, screenshot hoặc command history. `.env.example` không chứa key.

Mặc định base URL `https://api.deepseek.com`, model ID `deepseek-flash`; cấu hình đổi được. **Test kết nối thật** gửi request nhỏ có thể tính phí. Adapter dùng Chat Completions SSE, buffer JSON rồi validate; DeepSeek dùng `thinking: {type: disabled}`. Không hiển thị preview chưa validate. API lỗi không tự fallback sang demo; 400/401 không retry, transient retry tối đa một lần trước khi có content. Timeout/cancel đóng upstream.

Model chỉ nhận transcript gần đây, glossary và trích đoạn chọn lọc; không nhận API key trong prompt hoặc nguyên repository. Kiểm tra citation ID chỉ chứng minh nguồn tồn tại, không bảo đảm kết luận đúng nghĩa. Luôn xem lại nội dung quan trọng.

## Semantic local (tùy chọn)

```powershell
.\scripts\setup.ps1 -Semantic
```

Profile CPU dùng `torch==2.9.0+cpu`, `sentence-transformers==5.1.1`, `transformers==4.57.1`; dependency lock riêng. Trong Settings bấm **Tải / nạp E5 local** để tải model `intfloat/multilingual-e5-small` đã pin revision, chia lại passage theo tokenizer và publish generation có vector. Lần đầu cần mạng và dung lượng model; cache ở `.local/models` được giữ. Prefix `query:`/`passage:`, normalize và giới hạn 512 token được kiểm tra. Bật hybrid khi model đã nạp; restart chưa nạp model vẫn dùng FTS5 với nhãn rõ.

## Kiểm tra và phát triển

```powershell
.\scripts\test.ps1
# Dừng backend ở 8765 trước khi chạy browser tests:
.\scripts\test.ps1 -Browser
# Benchmark hybrid sau khi cài semantic profile:
.\.venv\Scripts\python.exe scripts\benchmark.py --semantic
```

Browser tests nạp **extension MV3 thật** vào Chromium của Playwright, dùng backend SQLite thật và DOM synthetic ở Meet origin bị route trong test. Không dùng profile Chrome cá nhân, không tạo cuộc họp, không gọi provider trả phí. Sidepanel document được thử ở 320 px; thao tác toolbar và Meet thật là gate riêng. Xem evidence trong `docs/evidence/`.

API prefix `/api/v1`; REST Bearer; WebSocket xác thực bằng frame đầu, Origin exact allowlist, Host loopback; không token query string. `/health` không auth, chỉ trả health. `/docs` và `/openapi.json` cũng cần token; schema đã lưu ở [docs/openapi.json](docs/openapi.json). TypeScript được sinh từ schema backend. Sau khi đổi contract:

```powershell
.\.venv\Scripts\python.exe scripts\export_openapi.py
npx openapi-typescript docs\openapi.json -o extension\src\api-schema.d.ts
npm run contracts
```

Để xem UI ở trình duyệt dev: set `MEET_DEV_ORIGIN=http://127.0.0.1:5173` trong environment backend, restart rồi `npm run dev -w extension`. UI hiện Browser preview; capture thật vẫn cần extension. Token preview chỉ giữ trong sessionStorage. Không thêm wildcard CORS.

## Xử lý lỗi

| Vấn đề | Cách kiểm tra |
| --- | --- |
| Backend chưa kết nối | Chạy start-backend, kiểm tra `http://127.0.0.1:8765/health`, pairing token và ID/Origin; chỉ cổng 8765 được manifest cho phép. |
| Chưa nhận caption | Bật captions, reload tab sau khi Load unpacked, chọn lại DOM; đợi lượt nói mới. Không có selector phù hợp thì trạng thái unknown/unsupported, không giả đang capture. |
| Im lặng | Không tự suy captions_off vì không có text. Muốn nhận diện toggle tắt rõ, profile cần selector toggle được quan sát; calibration cơ bản chỉ cho unknown nếu container mất. |
| Backend restart | Phiên local thành interrupted; Resume chủ động. Phiên RAM mất. Không tự tạo phiên khác. |
| Provider lỗi | Kiểm tra key/model/HTTPS URL. 401 cần key đúng; 429 chờ hoặc thử thủ công; timeout không fake success. |
| Thiếu FTS5 | Dùng official Python có SQLite FTS5; startup sẽ báo capability error. |
| E5 unavailable | Dùng keyword trước; cài optional lock, kiểm tra mạng/cache rồi nạp lại model. |
| Source sync lỗi | Xem lỗi/skip trong nguồn; generation tốt trước giữ với nhãn stale. Kiểm tra UTF-8, đường dẫn, kích thước và quyền đọc. |
| Report conflict | Local edit được giữ; xem phiên bản mới, đối chiếu và lưu chủ động. Export/copy dùng phiên bản đã lưu đang chọn. |

Giới hạn và checklist live: [docs/LIMITATIONS.md](docs/LIMITATIONS.md), [docs/CAPTION_ADAPTER.md](docs/CAPTION_ADAPTER.md), [docs/ACCEPTANCE_REPORT.md](docs/ACCEPTANCE_REPORT.md). Bộ tài liệu gốc được giữ nguyên trong `docs/spec/`; các cập nhật triển khai nằm ở `docs/`.

## Phân loại mức xử lý câu hỏi

Đã thêm 5 luồng local: nhanh, giải thích, phân tích sâu, hỏi lại/xác minh và tiếp tục nghe. Có preview/lý do, chọn mode thủ công và nút Phân tích sâu trên card. Auto nhường lượt thì không gọi AI; chọn nhanh không bỏ qua cờ cần xác minh. [Hành vi/API/giới hạn](docs/RESPONSE_ROUTING.md) · [Chức năng nên làm tiếp](docs/NEXT_PRIORITIES.md). Mục tiêu thời gian các luồng chưa được benchmark bằng provider thật; số đo 1,5 s trước đây thuộc build trước routing.

## Củng cố giai đoạn 1

Đã sửa tranh slot create/resume giữa local và RAM và chặn ba probe sai nghĩa gốc bằng guard có giới hạn, áp dụng qua pipeline/repair/map/merge. [Báo cáo A–E, phạm vi semantic và kết quả 82 fixture](docs/PHASE1_REPORT.md). Evidence mới nằm riêng trong docs/evidence/phase1; không thay bằng chứng lịch sử. Chưa nghiệm thu Meet thật hoặc đo provider/latency sau sửa.
