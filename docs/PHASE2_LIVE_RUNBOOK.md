# Nghiệm thu Meet thật — gate NOT TESTED

Chỉ dùng cuộc họp thử được phép, hai participant/tài khoản thử, không dùng cuộc họp khách hàng. Không tự gửi lời mời, chat hay disclosure. Người vận hành tổ chức buổi thử và thông báo mục đích theo quy định của mình. Provider trả phí cần quyền riêng cho lượt chạy; có thể thử capture mà chưa gọi AI.

## Chuẩn bị

1. Build `npm run build`, chạy backend một worker bằng `scripts/start-backend.ps1`, nạp `extension/dist` vào Chrome. Ghi commit (`git rev-parse HEAD`), version Chrome/OS/extension và ngày/timezone. Dùng profile Chrome thử riêng.
2. Mở Meet hai participant, bật caption. Tại side panel chọn DOM theo [CAPTION_ADAPTER.md](CAPTION_ADAPTER.md). Ghi selectors/profile/version đã thực sự quan sát. Không lấy selector synthetic làm selector Meet.
3. Tạo phiên local nếu cần xuất evidence. RAM mode chỉ kiểm tra trong ứng dụng, không dùng helper xuất ra disk. Ghi meeting ID. Chưa Start thì caption đang có sẽ bị prime/bỏ qua; bắt đầu bằng một lượt mới.
4. Để có ground truth **caption DOM**, mở DevTools trong tab Meet, dán [recorder](../scripts/caption-observation-recorder.js), rồi gọi `const recording = meetEXObservationRecorder(profile)` với profile đã chọn ở bước 2. Recorder chỉ giữ dữ liệu trong RAM tab, không gửi/lưu. Không in config/token. Lưu kết quả `recording.stop()` vào `.local/observations.json` khi xong, nếu chính sách phiên cho phép.

Recorder là một phép quan sát phụ cùng DOM, không phải ground truth lời nói. Mutation trong một JS task có thể bị coalesced trước cả hai observer; nếu cần kiểm chứng từng frame phải có người quan sát/ghi hình thử được phép độc lập. Không gọi caption-observed → rendered là speech → rendered.

## Hội thoại thử 15–20 phút

| Phút | Hành vi / lời thử | Đối chiếu |
| --- | --- | --- |
| 0–3 | Hai người lần lượt nói câu ngắn, “Yes”, “No, no”, câu dài khoảng 30 từ | Speaker là label, hai lượt Yes riêng, không mất từ lặp |
| 3–6 | “We can deploy”; tiếp đó “We cannot deploy”. “Timeout 15.5 milliseconds, API-17”; sửa “50.5 milliseconds, API-71” | Ghi DOM thật đã hiển thị gì; không ép Google phải tạo revision theo kịch bản |
| 6–8 | Lặp nguyên câu ở hai lượt, có người khác nói xen giữa; chờ im lặng một phút | Không global dedup; im lặng không tự thành captions_off |
| 8–10 | Pause; nói nội dung sentinel trong pause; Resume khi caption cũ còn hiện; nói lượt mới | Sentinel không vào transcript; không backfill; có gap pause |
| 10–12 | Đóng/mở panel, tiếp tục nói | Content/worker vẫn capture, panel không quyết định lifecycle |
| 12–14 | Ngắt mạng thử 5 giây rồi 20 giây; nói trong lúc ngắt; khôi phục | Transcript/ID/revision sau ACK, outbox về 0; nếu overflow phải có gap |
| 14–16 | Reload tab; Resume rõ ràng; mở tab Meet thứ hai | Reload interrupted, đoạn cũ không backfill; tab thứ hai không vào phiên |
| 16–20 | Tắt/bật captions; chọn lại DOM; End với caption cuối | Trạng thái trung thực; không hai observer; end có ACK hoặc cảnh báo flush timeout |

Ngắt backend là scenario riêng: local thành interrupted sau restart, phải Resume; RAM mất, không chuyển sang disk. Kill/restart service worker trong `chrome://extensions` rồi nói tiếp, kiểm tra outbox retry ID. Với tab đóng/chuyển mã phòng, kiểm tra interrupted và không ghi lời phòng mới. Thử overflow bằng replay, không cần làm tràn dữ liệu trong Meet thật.

## Ghi kết quả và phân loại lỗi

Copy [form](../fixtures/phase2/live-result-template.json) vào `.local`, điền từng scenario. So sánh chuỗi DOM với snapshot transcript theo speaker, thứ tự, text gốc, segment/revision, caption correction. Đếm **missing / duplicate / speaker mismatch / unapplied corrections** riêng. Đánh dấu ambiguity thay vì tự quyết định ground truth khi DOM không thể phân biệt hai lượt.

- **A — ASR Google:** caption đã sai so với câu người thử nói. Đối chiếu người quan sát/kịch bản, không gán lỗi này cho adapter.
- **B — ứng dụng:** caption đúng/đã thấy trong DOM nhưng meetEX mất, lặp, đổi text/speaker hoặc không áp correction. Không bỏ qua vì ASR cũng có lỗi.

Thu snapshot local bằng:

```powershell
.venv\Scripts\python.exe scripts/collect_phase2_evidence.py --meeting-id YOUR_ID --observations .local/observations.json
```

Helper đọc pairing token từ file riêng và không in; không gọi provider. Output giới hạn trong `.local`, từ chối xuất RAM meeting. Trong DevTools của worker có thể đọc riêng `await chrome.storage.session.get(['latencyRecords','captureTimings'])`; không đọc/in toàn bộ storage vì có config/token và transcript RAM. Chỉ xuất duration/ID khi được phép và đối chiếu cùng request trong `metrics.latency_records`.

`card_rendered_notification` là thông báo sau hai animation frame của card **đang hiển thị**, đo ở content script, gồm chi phí message. Không coi response đã validate nhưng panel đóng/card pinned là đã render. Báo manual/auto, cold/warm client, keyword/semantic, ready/stale/error/cancelled; n, median, nearest-rank p95, max và số mẫu không có render/correlation. Đo provider thật chỉ khi được phép; không dùng mẫu fixture để suy SLA.

Chưa ghi thông tin thực và đối chiếu đầy đủ thì giữ gate **NOT TESTED/PENDING_REVIEW**. Trước khi chia sẻ, bỏ tên người/mã phòng/token/nguồn riêng; không commit cuộc họp thật vào repository. Người dùng cần thực hiện buổi Meet trên và cung cấp kết quả đã ẩn danh để đóng gate.
