# Meet Copilot · Local

Trợ lý Anh–Việt cho developer trong Google Meet: đọc **phụ đề đang hiển thị**, tra nguồn dự án local, gợi ý có kiểm tra bằng chứng và soạn báo cáo để bạn xem lại. Chrome MV3 + FastAPI + SQLite WAL/FTS5; một người dùng, một process/worker sở hữu data directory. Semantic E5 CPU là tùy chọn.

**Bản hiện hành: 0.1.0 / protocol 1 / schema 2, Phase 5 candidate.** Nguồn trạng thái và gate nghiệm thu: [PHASE5_REPORT](docs/PHASE5_REPORT.md). Meet hai participant, chất lượng model của build mới và Windows độc lập vẫn **NOT TESTED**. Không gọi đây là production-ready hoặc MVP VERIFIED. Phase 1–4 là lịch sử: [mục lục](docs/README.md).

## Cài và chạy trên Windows

Cần Git, official Python **3.11+ có SQLite FTS5**, Node **22.12+** và npm. Đã dùng Python 3.13.4, Node 22.20.0 trên máy phát triển; CI khai báo Python 3.13 / Node 22.20.0 trên Windows và Ubuntu. Kết quả CI thực tế ghi riêng trong báo cáo.

```powershell
git clone --branch codex/phase5-local-operations https://github.com/hunter875/meetEX.git
cd meetEX
python scripts/meet.py setup
python scripts/meet.py build
python scripts/meet.py start
```

Setup dùng locks và `npm ci`, không cần admin, không thay execution policy; chạy lại giữ dữ liệu. Start chạy foreground tại **127.0.0.1:8765**. Chờ startup hoàn tất, dùng terminal khác chạy `python scripts/meet.py doctor`. Không tự dừng ứng dụng khác đang chiếm port. Ctrl+C hoặc `stop` dừng backend.

Dữ liệu mặc định ở `.local` dưới project. Đường dẫn tương đối trong `MEET_DATA_DIR` tính theo project. Có thể dùng `--data-dir 'D:\Meet Data'` nhất quán cho start/stop/doctor/backup/restore/rotate-token/update. Dùng directory chỉ tài khoản Windows của bạn quản lý.

## Nạp và pair extension

1. Mở `chrome://extensions`, bật Developer mode, **Load unpacked** → `extension/dist` trong checkout.
2. Copy ID extension, cấu hình exact Origin:

   ```powershell
   .\scripts\pair-extension.ps1 -ExtensionId YOUR_32_CHARACTER_EXTENSION_ID
   ```

3. Dừng/chạy lại backend. Mở Extension options → **Cài đặt**, nhập `http://127.0.0.1:8765`. Đọc file `.local/pairing-token` bằng editor local, dán vào ô password và **Lưu kết nối**. Với data directory riêng, đọc đúng file tại đó.
4. Pairing token khác **provider API key** và **meeting session**; chưa có key vẫn dùng demo được.

**Ngắt kết nối** xóa token và dữ liệu phiên tạm trong extension, dừng capture/reconnect; giữ meeting đã lưu ở backend. `python scripts/meet.py rotate-token` hủy token cũ ở REST và WebSocket, yêu cầu pair lại. Không tự in token vào diagnostics.

## Thử demo và Meet

Giữ backend chạy, thực hiện `.\scripts\load-demo.ps1`. Chọn project DEMO trong **Đang họp**, bật **Chế độ demo có nhãn**, Start, thêm caption, tạo gợi ý, End rồi tạo/edit/export report. Demo là output kiểm soát, không phải chất lượng model thật.

Provider key chỉ ở RAM/environment; đặt trong Settings cho lần chạy này. **Test kết nối thật** có thể tính phí. Doctor/test mặc định không gọi provider trả phí.

Khi dùng Meet: bật caption tiếng Anh, mở side panel, chọn vùng caption/speaker ở lần đầu, Start đúng tab/meeting, đợi lượt mới. Pause/resume không backfill. Giữ card không dừng capture. Xem evidence trước khi nói/gửi báo cáo. [Runbook và gate Meet thật](docs/PHASE2_LIVE_RUNBOOK.md).

## Lệnh vận hành

```powershell
python scripts/meet.py doctor
python scripts/meet.py test --browser
python scripts/meet.py stop
python scripts/meet.py backup --path 'D:\Meet Backups\snapshot-01'
python scripts/meet.py restore --path 'D:\Meet Backups\snapshot-01'
python scripts/meet.py rotate-token
```

Backup dùng SQLite backup API, nhất quán với WAL; chỉ chứa DB local và manifest/checksum. Không gồm RAM meetings, token, provider key, .env, model cache hoặc file nguồn ngoài repo. Restore yêu cầu backend dừng, validate rồi thay DB atomically; giữ preimage ở `DATA_DIR/recovery`. Không copy riêng file SQLite đang mở.

Update: End meeting, stop, chọn source commit/nhánh mới, rồi:

```powershell
python scripts/meet.py update --path 'D:\Meet Backups\before-update-01'
python scripts/meet.py start
python scripts/meet.py doctor
```

Reload extension ở **cùng thư mục unpacked**, kiểm tra ID/Origin và pair lại nếu đổi. Không uninstall extension để update. Rollback source không đồng nghĩa downgrade schema: [runbook nâng cấp/khôi phục](docs/LOCAL_OPERATIONS.md).

```powershell
python scripts/meet.py setup --semantic  # tùy chọn, cần mạng/dung lượng model
python scripts/meet.py package           # artifact local từ Git commit sạch
```

E5 thiếu/chưa nạp vẫn chạy FTS5 với nhãn từ khóa. Windows là nền tảng nghiệm thu chính; Linux development/CI chỉ trong phạm vi có bằng chứng riêng. [Kiến trúc](docs/ARCHITECTURE.md), [API](docs/openapi.json), [báo cáo/gate](docs/PHASE5_REPORT.md).

Không thu audio, tự phát ngôn/gửi chat/email, chạy code/SQL của nguồn, kết nối production DB hoặc thêm cloud/multiuser. Source/build bàn giao không chứa credential, DB cá nhân, node_modules, venv hay model cache.
