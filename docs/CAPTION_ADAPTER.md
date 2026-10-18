# Caption adapter · calibrated profile + Phase 2 capture

**Chưa kiểm chứng trên Meet thật.** Kết quả hiện tại: [Phase 2 A–G](PHASE2_REPORT.md), [56 frontend tests](evidence/phase2/frontend-final.json), [4 browser E2E](evidence/phase2/browser-final-results.json). Profile `meet-calibrated-v1` đang lưu vẫn tương thích; capture algorithm theo source commit Phase 2, default reducer version v2. Profile không chứng minh DOM Meet live.

Không có selector production viết từ trí nhớ. Profile ban đầu rỗng → `unsupported_dom`. Khi người dùng chủ động chọn DOM đang hiển thị, extension tạo selector từ các element được chọn. Đây là adapter phụ thuộc giao diện, không phải API Google.

## Chọn vùng phụ đề

1. Mở Meet, bật phụ đề, đợi một đoạn có speaker/câu nói. Mở side panel → **Chọn DOM / Chọn vùng phụ đề Meet**.
2. Chọn container chỉ chứa caption blocks. Nếu mới chọn một chữ, dùng **Mở rộng** để chọn container; không chọn chat, toàn trang, toolbar hoặc danh sách participant. HTML/body bị từ chối.
3. Xác nhận container, chọn element chứa **toàn bộ chữ của một câu**, xác nhận; chọn speaker trong cùng block hoặc Bỏ qua.
4. Profile lưu trong trusted extension storage, gồm root/block/text/speaker, version và calibrated_at. Các selector con có `:scope >` để giới hạn trong nhánh đã quan sát. Chỉ block sibling cuối được bỏ nth-of-type để nhận các turn tương ứng.
5. Hủy/chọn lại nếu cấu trúc chưa phù hợp. Đợi lượt nói mới: đoạn đang render khi Start/Resume bị bỏ qua để không thu lại lịch sử trước đó.

Profile synthetic dùng trong tests như `#captions .block .words` **chỉ nằm trong test**, không phải profile mặc định cho Google Meet. DOM Meet có thể khác giữa tài khoản, ngôn ngữ và rollout; cần đối chiếu transcript thực tế sau mỗi lần chọn.

## Hành vi

- MutationObserver chỉ quan sát caption root, đọc ngay mỗi batch đã giao. Watchdog tìm lại root mỗi 500 ms; timer ổn định riêng 100 ms. Stable mặc định sau 1000 ms không đổi, là heuristic, không phải final flag Google. Stop/off disconnect observer; stop dọn timer, không để instance calibration cũ tiếp tục chạy.
- Cùng turn sửa text → cùng segment ID, revision tăng. Event ID giữ nguyên khi retry; capture_epoch thay khi document/adapter khởi động lại. Speaker đổi hoặc turn mới rõ ràng → segment mới. Không global dedup text.
- Node replacement đối chiếu unique candidate vừa mất, độc lập slot; kết hợp speaker, timing và lexical anchors, không dùng similarity một mình. Cửa sổ text có overlap giữ prefix đã thấy, raw text không bị normalize. [Ngưỡng/giới hạn chưa hiệu chuẩn live](PHASE2_REPORT.md). Hai câu y hệt không có lifecycle signal và correction ngoài phần còn hiện vẫn mơ hồ.
- Mất container → reattach, status unknown/unsupported và gap. Im lặng không suy ra captions_off. Toggle chỉ được coi off khi profile có selector được quan sát và `aria-pressed=false`; calibration cơ bản không tự đoán toggle/meeting-left.
- Adapter heartbeat 20 giây, độc lập WebSocket heartbeat. Mất heartbeat adapter thì capture unknown/gap; backend connected không có nghĩa caption đang thu.
- Worker kiểm tra sender extension ID, Meet origin, tab, document và meeting path; DOM không được chọn project/session hoặc fetch URL tùy ý.
- Chuyển khỏi Meet, đóng tab, đổi meeting hoặc reload document làm interrupted. Reload cập nhật document nhưng đòi Resume rõ ràng, bỏ pending cũ kèm warning và prime caption đang hiện. Đóng panel không dừng content script. Backend chặn socket document/connection cũ sau rebind.
- Outbox RAM giới hạn 500 events / 5 MiB. ACK rồi mới xóa, retry cùng ID sau ≥2 s cả khi socket còn sống. Overflow/End thiếu ACK có gap. Gap mới có ID/ACK/retry riêng. Pause không mang pending chưa ACK sang Resume; bỏ có reason trong backend. Backend restart local yêu cầu Resume; RAM mất, không chuyển disk.

UI hiển thị backend connected, content alive, adapter status, pending và nguy cơ thiếu dữ liệu riêng. Heartbeat không chứng minh selector đúng. [Runbook 15–20 phút, recorder và form](PHASE2_LIVE_RUNBOOK.md) dùng để đóng gate thật.

## Checklist đóng gate Meet thật

Chỉ dùng meeting do bạn sở hữu/được phép thử, ít nhất hai participant. Ghi Chrome/version, ngôn ngữ Meet/caption, profile selector, adapter version và thời điểm; không lưu token/key trong evidence.

- [ ] Bật caption tiếng Anh, chọn DOM, Start tại đúng tab/project; đối chiếu nguyên văn và dấu phủ định/số.
- [ ] Câu dài cập nhật partial, sửa sau stable; không nhân bản cả câu.
- [ ] Hai speaker cùng nói “Yes”; một speaker nói lại sau turn khác.
- [ ] Im lặng 60 giây; tắt/bật caption; đổi ngôn ngữ UI.
- [ ] Container render lại/node recycle; có gap hoặc phục hồi đúng, không đọc chat/controls.
- [ ] Đóng/mở side panel; đổi tab và quay lại; một tab Meet khác không vào phiên cũ.
- [ ] Pause/Resume không thu bù phần pause. Ngắt backend 20 giây, reconnect đúng ACK/replay/gap.
- [ ] Restart worker và backend; active local thành interrupted sau backend restart. RAM session mất và cache được bỏ.
- [ ] End hai lần, flush caption cuối; native side panel mở từ user gesture.

Chưa có phiên hai participant để chạy checklist này; tất cả dòng live vẫn NOT TESTED. Không dùng fixture pass để đóng gate.

Nguồn: [Google Meet captions](https://support.google.com/meet/answer/15077804?hl=en), [Chrome sidePanel](https://developer.chrome.com/docs/extensions/reference/api/sidePanel), [WebSocket service worker](https://developer.chrome.com/docs/extensions/how-to/web-platform/websockets), [extension cross-origin requests](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests).
