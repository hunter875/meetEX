import { Outbox } from "./outbox";
import type { CaptionProfile } from "../content/meet-adapter";
type Binding = {
  session_id: string;
  tab_id: number;
  document_id: string;
  meeting_key: string;
  status: string;
  demo?: boolean;
};
type Config = { url: string; token: string; profile?: CaptionProfile };
let config: Config = { url: "http://127.0.0.1:8765", token: "" };
let binding: Binding | null = null;
let outbox = new Outbox();
let socket: WebSocket | null = null;
let authenticated = false;
let bound = false;
let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
let heartbeat: ReturnType<typeof setInterval> | undefined;
let attempts = 0;
let blocked = false;
let pendingGap = false;
let ready: Promise<void>;
let serial = Promise.resolve<unknown>(undefined);
let captureTimings: number[] = [];
let interruptionGap = false;
let lastAdapterHeartbeat = 0;
let adapterHeartbeatLost = false;
let captureRejected = false;
let lastAdapterStatus = "starting";
let pendingReasons = new Set<string>();
let reasonIDs: Record<string, string> = {};
let pairingStatus = "unpaired";
let connecting = false;
const sentAt = new Map<string, number>();
function drain() {
  if (!bound || binding?.status !== "active") return;
  const pending = new Set(outbox.items.map((p) => p.event.event_id));
  for (const id of sentAt.keys()) if (!pending.has(id)) sentAt.delete(id);
  for (const p of outbox.items) {
    const at = sentAt.get(p.event.event_id);
    if (at === undefined || performance.now() - at >= 2000) {
      captureSend("caption.upsert", p.event);
      sentAt.set(p.event.event_id, performance.now());
    }
  }
  for (const reason of pendingReasons)
    captureSend("capture.gap", { reason, event_id: reasonIDs[reason] });
}
function gap(reason: string) {
  pendingReasons.add(reason);
  reasonIDs[reason] ||= crypto.randomUUID();
  void persist();
  if (bound)
    captureSend("capture.gap", { reason, event_id: reasonIDs[reason] });
}
const extensionPage = (sender: chrome.runtime.MessageSender) =>
  sender.id === chrome.runtime.id &&
  !!sender.url?.startsWith(chrome.runtime.getURL(""));
const meetingKey = (url: string) => {
  const parsed = new URL(url);
  if (parsed.origin !== "https://meet.google.com")
    throw new Error("Chọn một tab Google Meet");
  return parsed.pathname;
};
const configURL = (url: string) => {
  const u = new URL(url);
  if (
    u.protocol !== "http:" ||
    !["127.0.0.1", "localhost"].includes(u.hostname) ||
    u.port !== "8765" ||
    u.pathname !== "/" ||
    u.username ||
    u.password ||
    u.search ||
    u.hash
  )
    throw new Error(
      "Backend URL phải là http://127.0.0.1:8765 hoặc http://localhost:8765",
    );
  return u.origin;
};
const notify = (message: unknown) =>
  chrome.runtime.sendMessage(message).catch(() => {});
const persist = () =>
  chrome.storage.session.set({
    binding,
    pending: outbox.items,
    pendingGap,
    interruptionGap,
    captureRejected,
    lastAdapterStatus,
    pendingReasons: [...pendingReasons],
    reasonIDs,
  });
const captureSend = (type: string, payload: unknown) => {
  if (socket?.readyState === WebSocket.OPEN && authenticated)
    socket.send(
      JSON.stringify({
        type,
        protocol_version: 1,
        session_id: binding?.session_id,
        ...(type === "caption.upsert"
          ? { event_id: (payload as { event_id: string }).event_id }
          : {}),
        payload,
      }),
    );
};
async function request(path: string, method = "GET", body?: unknown) {
  if (!path.startsWith("/api/v1/")) throw new Error("Invalid API route");
  const response = await fetch(config.url + path, {
    method,
    headers: {
      Authorization: "Bearer " + config.token,
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.message || data.code || `HTTP ${response.status}`);
  return data;
}
async function startCapture() {
  if (!binding || binding.demo || binding.status !== "active") return;
  lastAdapterStatus = "starting";
  await chrome.tabs
    .sendMessage(
      binding.tab_id,
      { type: "capture.start", profile: config.profile || null },
      { documentId: binding.document_id },
    )
    .catch(() => {
      lastAdapterStatus = "unknown";
      gap("adapter_heartbeat_lost");
      void notify({
        type: "transport.error",
        error: "Reload tab Meet để nạp content script",
      });
    });
}
async function forgetSession(id: string) {
  await chrome.storage.session.remove("reading_" + id);
  if (binding?.session_id === id) {
    const tab = binding.tab_id;
    binding = null;
    bound = false;
    outbox = new Outbox();
    pendingGap = false;
    interruptionGap = false;
    pendingReasons.clear();
    reasonIDs = {};
    await persist();
    if (tab >= 0)
      await chrome.tabs
        .sendMessage(tab, { type: "capture.stop" })
        .catch(() => {});
  }
}
async function reconcile() {
  try {
    const sessions = await request("/api/v1/meetings");
    const valid = new Set(sessions.map((m: { id: string }) => m.id));
    const values = await chrome.storage.session.get(null);
    for (const key of Object.keys(values))
      if (key.startsWith("reading_") && !valid.has(key.slice(8)))
        await chrome.storage.session.remove(key);
    if (binding && !valid.has(binding.session_id))
      await forgetSession(binding.session_id);
  } catch {
    /* Keep recoverable RAM state while backend is temporarily unavailable. */
  }
}
async function connect() {
  if (
    socket &&
    (socket.readyState === WebSocket.CONNECTING ||
      socket.readyState === WebSocket.OPEN)
  )
    return;
  if (blocked || !config.token || connecting) return;
  connecting = true;
  const credential = config.token;
  try {
    const response = await fetch(config.url + "/ready", {
      signal: AbortSignal.timeout(3000),
    });
    const status = await response.json();
    if (status.protocol_version !== 1 || status.app_version !== "0.1.0") {
      blocked = true;
      pairingStatus = "incompatible";
      void notify({
        type: "transport.error",
        error:
          "Backend và extension không tương thích. Cập nhật cả hai rồi pair lại.",
      });
      return;
    }
    if (!status.ready) throw new Error("Backend is starting or stopping");
  } catch {
    if (!blocked && config.token === credential)
      reconnectTimer = setTimeout(() => void connect(), 2000);
    return;
  } finally {
    connecting = false;
    if (!blocked && config.token && config.token !== credential) void connect();
  }
  if (blocked || !config.token || config.token !== credential) return;
  const ws = new WebSocket(
    config.url.replace("http:", "ws:") + "/api/v1/events",
  );
  socket = ws;
  authenticated = false;
  bound = false;
  ws.onopen = () =>
    ws.send(
      JSON.stringify({
        type: "auth",
        protocol_version: 1,
        token: config.token,
      }),
    );
  ws.onmessage = (event) => {
    if (socket !== ws) return;
    const msg = JSON.parse(String(event.data));
    if (msg.type === "auth.ok") {
      authenticated = true;
      pairingStatus = "paired";
      attempts = 0;
      void notify({ type: "transport.status", status: "connected" });
      void reconcile().then(() => {
        if (binding && binding.status === "active" && !binding.demo)
          captureSend("session.bind", {
            tab_id: binding.tab_id,
            document_id: binding.document_id,
            meeting_key: binding.meeting_key,
          });
      });
      if (heartbeat) clearInterval(heartbeat);
      heartbeat = setInterval(() => {
        captureSend("heartbeat", {});
        if (
          binding?.status === "active" &&
          !binding.demo &&
          Date.now() - lastAdapterHeartbeat > 45000 &&
          !adapterHeartbeatLost
        ) {
          captureSend("capture.status", { status: "unknown" });
          gap("adapter_heartbeat_lost");
          adapterHeartbeatLost = true;
        }
      }, 20000);
    } else if (msg.type === "auth.error") {
      blocked = true;
      pairingStatus = "invalid";
      ws.close();
      void notify({
        type: "transport.error",
        error: "Pairing token không hợp lệ; nhập token mới để pair lại",
      });
    } else if (
      msg.type === "session.snapshot" &&
      binding &&
      binding.session_id === msg.session_id
    ) {
      binding.status = msg.payload.snapshot.status;
      if (binding.status === "active") {
        bound = true;
        sentAt.clear();
        drain();
        if (pendingReasons.size) gap([...pendingReasons][0]);
        if (pendingGap) {
          gap("outbox_overflow");
          pendingGap = false;
        }
        if (interruptionGap) {
          gap("interrupted_pending_discarded");
          interruptionGap = false;
        }
        void startCapture();
      } else bound = false;
      void persist();
    } else if (msg.type === "capture.gap.ack") {
      if (reasonIDs[msg.reason] === msg.event_id) {
        pendingReasons.delete(msg.reason);
        delete reasonIDs[msg.reason];
        void persist();
      }
    } else if (msg.type === "caption.ack") {
      if (msg.applied && captureRejected) {
        captureRejected = false;
        captureSend("capture.status", { status: lastAdapterStatus });
      }
      if (binding && !binding.demo)
        void chrome.tabs
          .sendMessage(
            binding.tab_id,
            { type: "capture.ack", event_id: msg.event_id },
            { documentId: binding.document_id },
          )
          .catch(() => {});
      outbox.ack(msg.event_id);
      sentAt.delete(msg.event_id);
      void persist();
    } else if (msg.type === "meeting.deleted") {
      void forgetSession(msg.payload.meeting_id);
    } else if (msg.type === "error") {
      if (
        msg.event_id &&
        outbox.items.some((p) => p.event.event_id === msg.event_id)
      ) {
        outbox.ack(msg.event_id);
        captureRejected = true;
        captureSend("capture.status", { status: "unknown" });
        gap("event_rejected");
        void persist();
        void notify({
          type: "transport.error",
          error: "Caption bị backend từ chối: " + msg.payload.message,
        });
      }
      if (
        [
          "SESSION_INTERRUPTED",
          "SESSION_SCOPE",
          "BINDING_SCOPE",
          "NOT_FOUND",
        ].includes(msg.payload?.code)
      ) {
        bound = false;
        void notify({ type: "transport.error", error: msg.payload.message });
        if (binding) {
          void chrome.tabs
            .sendMessage(binding.tab_id, { type: "capture.stop" })
            .catch(() => {});
          if (msg.payload.code === "NOT_FOUND") {
            void chrome.storage.session.remove("reading_" + binding.session_id);
            binding = null;
            outbox = new Outbox();
          } else if (msg.payload.code === "SESSION_INTERRUPTED") {
            binding.status = "interrupted";
            if (outbox.items.length) interruptionGap = true;
            outbox = new Outbox();
          }
          void persist();
        }
      }
    }
    if (
      msg.type === "suggestion.scheduled" &&
      binding &&
      binding.session_id === msg.session_id &&
      !binding.demo
    )
      void chrome.tabs
        .sendMessage(
          binding.tab_id,
          { type: "capture.scheduled", payload: msg.payload },
          { documentId: binding.document_id },
        )
        .catch(() => {});
    void notify({ type: "server.event", event: msg });
  };
  ws.onclose = (event) => {
    if (socket !== ws) return;
    socket = null;
    authenticated = false;
    bound = false;
    if (heartbeat) clearInterval(heartbeat);
    void notify({ type: "transport.status", status: "disconnected" });
    if (event.code === 4401 || event.code === 4403) {
      blocked = true;
      pairingStatus = "invalid";
      void notify({
        type: "transport.error",
        error:
          "Pairing đã hết hiệu lực hoặc Origin không khớp; nhập token mới và kiểm tra extension ID",
      });
      return;
    }
    if (!blocked) {
      const ms = Math.min(15000, 1000 * 2 ** attempts++) + Math.random() * 300;
      reconnectTimer = setTimeout(connect, ms);
    }
  };
}
async function handle(
  message: any,
  sender: chrome.runtime.MessageSender,
): Promise<any> {
  await ready;
  if (message.type?.startsWith("capture.") && sender.tab) {
    if (
      sender.id !== chrome.runtime.id ||
      !sender.url?.startsWith("https://meet.google.com/")
    )
      throw new Error("Untrusted caption sender");
    if (message.type === "capture.hello") {
      if (
        binding &&
        binding.tab_id === sender.tab.id &&
        binding.meeting_key === meetingKey(sender.url) &&
        sender.documentId
      ) {
        const changed = binding.document_id !== sender.documentId;
        if (changed) {
          await interrupt("document_reloaded");
          binding.document_id = sender.documentId;
          await persist();
        }
      }
      await chrome.storage.session.set({
        ["document_" + sender.tab.id]: sender.documentId,
      });
      return { ok: true };
    }
    if (message.type === "capture.profile") {
      if (
        binding &&
        ["active", "paused"].includes(binding.status) &&
        (sender.tab.id !== binding.tab_id ||
          sender.documentId !== binding.document_id ||
          meetingKey(sender.url) !== binding.meeting_key)
      )
        throw new Error("Calibration belongs to another tab/document");
      config.profile = message.payload;
      await chrome.storage.local.set({ config });
      if (binding?.status === "active") await startCapture();
      return { ok: true };
    }
    if (
      !binding ||
      sender.tab.id !== binding.tab_id ||
      sender.documentId !== binding.document_id ||
      meetingKey(sender.url) !== binding.meeting_key
    )
      throw new Error("Caption belongs to an unbound tab/document");
    lastAdapterHeartbeat = Date.now();
    adapterHeartbeatLost = false;
    if (message.type === "capture.caption" && binding.status === "active") {
      if (outbox.push(message.payload) > 0) pendingGap = true;
      await persist();
      drain();
      return { ok: true };
    }
    if (
      message.type === "capture.status" ||
      message.type === "capture.heartbeat"
    ) {
      lastAdapterStatus = message.payload.status;
      if (bound)
        captureSend(
          "capture.status",
          captureRejected ? { status: "unknown" } : message.payload,
        );
    }
    if (message.type === "capture.gap") gap(message.payload.reason);
    if (message.type === "capture.latency") {
      const records =
        (await chrome.storage.session.get("latencyRecords")).latencyRecords ||
        [];
      // Content sends only IDs and durations; never copy caption text into telemetry.
      records.push({ ...message.payload, meeting_id: binding.session_id });
      await chrome.storage.session.set({
        latencyRecords: records.slice(-1000),
      });
      return { ok: true };
    }
    if (message.type === "capture.measurement") {
      const ms = message.payload?.duration_ms;
      if (
        typeof ms === "number" &&
        Number.isFinite(ms) &&
        ms >= 0 &&
        ms <= 600000
      ) {
        captureTimings.push(ms);
        captureTimings = captureTimings.slice(-1000);
        await chrome.storage.session.set({ captureTimings });
        void notify({ type: "capture.timing", duration_ms: ms });
      }
    }
    return { ok: true };
  }
  if (!extensionPage(sender))
    throw new Error("Only extension UI may control sessions/settings");
  if (message.type === "ui.state")
    return {
      ok: true,
      config,
      binding,
      connected: authenticated,
      pairing_status: pairingStatus,
      pending: outbox.items.length,
      extension_id: chrome.runtime.id,
      capture_timings: captureTimings,
      capture_diagnostics: {
        backend_connected: authenticated,
        content_alive: Date.now() - lastAdapterHeartbeat <= 45000,
        adapter_status:
          binding?.status === "ended"
            ? "meeting_left"
            : binding?.status === "paused"
              ? "paused"
              : !authenticated || binding?.status === "interrupted"
                ? "disconnected"
                : Date.now() - lastAdapterHeartbeat > 45000
                  ? "unknown"
                  : lastAdapterStatus,
        pending_gap: pendingGap || pendingReasons.size > 0,
      },
    };
  if (message.type === "ui.disconnect") {
    blocked = true;
    pairingStatus = "unpaired";
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (heartbeat) clearInterval(heartbeat);
    if (binding) await interrupt("user_disconnect");
    const previous = socket;
    socket = null;
    previous?.close();
    authenticated = false;
    bound = false;
    binding = null;
    outbox = new Outbox();
    sentAt.clear();
    pendingReasons.clear();
    reasonIDs = {};
    pendingGap = false;
    interruptionGap = false;
    config = { ...config, token: "" };
    await chrome.storage.local.set({ config });
    await chrome.storage.session.clear();
    await persist();
    void notify({ type: "transport.status", status: "disconnected" });
    return { ok: true };
  }
  if (message.type === "ui.card_rendered") {
    if (binding && !binding.demo && message.meeting_id === binding.session_id)
      await chrome.tabs
        .sendMessage(
          binding.tab_id,
          { type: "capture.rendered", payload: message.payload },
          { documentId: binding.document_id },
        )
        .catch(() => {});
    return { ok: true };
  }
  if (message.type === "ui.config") {
    config = {
      ...config,
      url: configURL(message.config.url),
      token: message.config.token,
    };
    blocked = false;
    pairingStatus = config.token ? "connecting" : "unpaired";
    await chrome.storage.local.set({ config });
    if (reconnectTimer) clearTimeout(reconnectTimer);
    const previous = socket;
    socket = null;
    previous?.close();
    connect();
    return { ok: true };
  }
  if (message.type === "ui.dashboard") {
    await chrome.tabs.create({
      url:
        chrome.runtime.getURL("dashboard.html") +
        "#" +
        (message.route || "/projects"),
    });
    return { ok: true };
  }
  if (message.type === "ui.calibrate") {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    if (!tab?.id || !tab.url?.startsWith("https://meet.google.com/"))
      throw new Error("Mở tab Google Meet và bật caption trước");
    return chrome.tabs.sendMessage(tab.id, { type: "capture.calibrate" });
  }
  if (message.type === "ui.bind") {
    const m = await request("/api/v1/meetings/" + message.session_id);
    if (binding?.session_id !== m.id) {
      captureRejected = false;
      bound = false;
      outbox = new Outbox();
      sentAt.clear();
      pendingGap = false;
      interruptionGap = false;
      pendingReasons.clear();
      reasonIDs = {};
      if (binding && !binding.demo)
        await chrome.tabs
          .sendMessage(
            binding.tab_id,
            { type: "capture.stop" },
            { documentId: binding.document_id },
          )
          .catch(() => {});
    }
    if (m.demo) {
      binding = {
        session_id: m.id,
        tab_id: -1,
        document_id: "demo",
        meeting_key: "demo",
        status: m.status,
        demo: true,
      };
      await persist();
      return { ok: true };
    }
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    if (!tab?.id || !tab.url) throw new Error("Chọn tab Meet đang họp");
    const key = meetingKey(tab.url);
    if (m.meeting_key !== key) throw new Error("Phiên thuộc một meeting khác");
    const doc = (await chrome.storage.session.get("document_" + tab.id))[
      "document_" + tab.id
    ];
    if (!doc) throw new Error("Reload tab Meet để nhận document binding");
    binding = {
      session_id: m.id,
      tab_id: tab.id,
      document_id: doc,
      meeting_key: key,
      status: m.status,
    };
    await persist();
    connect();
    if (authenticated)
      captureSend("session.bind", {
        tab_id: tab.id,
        document_id: doc,
        meeting_key: key,
      });
    return { ok: true };
  }
  if (message.type === "ui.meet-tab") {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    if (!tab?.id || !tab.url) throw new Error("Mở tab Meet trước");
    return { ok: true, meeting_key: meetingKey(tab.url) };
  }
  if (message.type === "ui.control") {
    if (!binding) throw new Error("Chưa có binding");
    let flushTimeout = false;
    if (message.action === "end" && !binding.demo) {
      await chrome.tabs
        .sendMessage(binding.tab_id, { type: "capture.flush" })
        .catch(() => {});
      await new Promise((resolve) => setTimeout(resolve, 40));
      await serial;
      const until = Date.now() + 2000;
      while (outbox.items.length && Date.now() < until)
        await new Promise((resolve) => setTimeout(resolve, 30));
      if (outbox.items.length) {
        flushTimeout = true;
        gap("end_flush_timeout");
      }
    }
    const oldStatus = binding.status;
    if (message.action !== "resume") {
      binding.status = message.action === "pause" ? "paused" : "interrupted";
      bound = false;
      if (!binding.demo)
        await chrome.tabs
          .sendMessage(
            binding.tab_id,
            { type: "capture.stop" },
            { documentId: binding.document_id },
          )
          .catch(() => {});
      await serial;
    }
    const discarded = outbox.items.length > 0 && message.action !== "resume";
    let result;
    try {
      result = await request(
        "/api/v1/meetings/" + binding.session_id + "/control",
        "POST",
        {
          action: message.action,
          idempotency_key: message.idempotency_key,
          ...(flushTimeout
            ? { reason: "end_flush_timeout" }
            : discarded
              ? { reason: "interrupted_pending_discarded" }
              : {}),
        },
      );
    } catch (error) {
      binding.status = oldStatus === "active" ? "interrupted" : oldStatus;
      await persist();
      throw error;
    }
    binding.status = result.status;
    if (discarded) {
      outbox = new Outbox();
      sentAt.clear();
    }
    if (message.action === "resume" && !binding.demo) {
      if (authenticated)
        captureSend("session.bind", {
          tab_id: binding.tab_id,
          document_id: binding.document_id,
          meeting_key: binding.meeting_key,
        });
      else connect();
    } else if (!binding.demo)
      await chrome.tabs
        .sendMessage(binding.tab_id, { type: "capture.stop" })
        .catch(() => {});
    if (message.action === "end") {
      outbox = new Outbox();
      pendingGap = false;
    }
    await persist();
    return { ok: true, result };
  }
  throw new Error("Unknown extension command");
}
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (
    [
      "server.event",
      "transport.status",
      "transport.error",
      "capture.timing",
    ].includes(message.type)
  )
    return false;
  const work = message.type?.startsWith("capture.")
    ? (serial = serial.then(
        () => handle(message, sender),
        () => handle(message, sender),
      ))
    : handle(message, sender);
  work
    .then(respond)
    .catch((error) => respond({ ok: false, error: String(error.message) }));
  return true;
});
async function interrupt(reason: string) {
  if (!binding || !["active", "paused"].includes(binding.status)) return;
  const id = binding.session_id;
  binding.status = "interrupted";
  bound = false;
  if (outbox.items.length) interruptionGap = true;
  outbox = new Outbox();
  sentAt.clear();
  await persist();
  if (!binding.demo)
    await chrome.tabs
      .sendMessage(
        binding.tab_id,
        { type: "capture.stop" },
        { documentId: binding.document_id },
      )
      .catch(() => {});
  await request("/api/v1/meetings/" + id + "/control", "POST", {
    action: "interrupt",
    idempotency_key: crypto.randomUUID(),
    reason,
  }).catch(() => {});
}
chrome.tabs.onRemoved.addListener((tabId) => {
  void ready.then(async () => {
    if (binding?.tab_id === tabId) await interrupt("tab_closed");
  });
});
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (change.url || change.status === "loading")
    void ready
      .then(async () => {
        if (binding?.tab_id === tabId) {
          let changed = true;
          try {
            const tab = await chrome.tabs.get(tabId);
            changed =
              meetingKey(change.url || tab.url || "") !== binding.meeting_key;
          } catch {
            /* New origin is outside the granted Meet host permission. */
          }
          if (changed) await interrupt("tab_navigated");
        }
      })
      .catch(() => {});
});
chrome.runtime.onInstalled.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});
chrome.alarms.onAlarm.addListener(() => void ready.then(() => connect()));
ready = (async () => {
  await chrome.storage.local.setAccessLevel({
    accessLevel: "TRUSTED_CONTEXTS",
  });
  await chrome.storage.session.setAccessLevel({
    accessLevel: "TRUSTED_CONTEXTS",
  });
  const local = await chrome.storage.local.get("config");
  config = { ...config, ...local.config };
  const state = await chrome.storage.session.get([
    "binding",
    "pending",
    "pendingGap",
    "captureTimings",
    "interruptionGap",
    "captureRejected",
    "lastAdapterStatus",
    "pendingReasons",
    "reasonIDs",
  ]);
  binding = state.binding || null;
  outbox = new Outbox(state.pending || []);
  pendingGap = state.pendingGap || outbox.droppedOnRestore > 0;
  captureTimings = state.captureTimings || [];
  interruptionGap = state.interruptionGap || false;
  captureRejected = state.captureRejected || false;
  lastAdapterStatus = "unknown";
  pendingReasons = new Set(state.pendingReasons || []);
  reasonIDs = state.reasonIDs || {};
  for (const reason of pendingReasons)
    reasonIDs[reason] ||= crypto.randomUUID();
  if (binding) {
    try {
      const m = await request("/api/v1/meetings/" + binding.session_id);
      binding.status = m.status;
      if (m.status !== "active" && outbox.items.length) {
        interruptionGap = true;
        outbox = new Outbox();
        await persist();
      }
    } catch {}
  }
  await chrome.alarms.create("transport-recovery", { periodInMinutes: 1 });
  connect();
  setInterval(() => {
    drain();
    if (bound && pendingGap) {
      gap("outbox_overflow");
      pendingGap = false;
      void persist();
    }
  }, 1000);
})();
