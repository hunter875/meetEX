import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { components } from "../api-schema";
export type LocalConfig = { url: string; token: string };
type RuntimeState = {
  config: LocalConfig;
  binding: { session_id: string; status: string; demo?: boolean } | null;
  connected: boolean;
  pairing_status?: string;
  pending: number;
  extension_id: string;
  capture_timings?: number[];
  capture_diagnostics?: components["schemas"]["CaptureDiagnosticsDTO"];
};
const isExtension = typeof chrome !== "undefined" && !!chrome.runtime?.id;
export const inExtension = isExtension;
export async function runtime(message: unknown): Promise<any> {
  if (!isExtension)
    throw new Error("Thao tác này cần Chrome extension side panel");
  const result = await chrome.runtime.sendMessage(message);
  if (result?.ok === false)
    throw new Error(result.error || "Extension request failed");
  return result;
}
export class APIError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}
type API = <T = any>(
  path: string,
  method?: string,
  body?: unknown,
  asText?: boolean,
) => Promise<T>;
type Context = {
  api: API;
  config: LocalConfig;
  state: RuntimeState | null;
  loading: boolean;
  revision: number;
  refresh: () => void;
  saveConfig: (config: LocalConfig) => Promise<void>;
  toast: (text: string) => void;
};
const AppContext = createContext<Context>(null!);
export function AppProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<LocalConfig>({
    url: "http://127.0.0.1:8765",
    token: "",
  });
  const [state, setState] = useState<RuntimeState | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [notice, setNotice] = useState("");
  const refresh = useCallback(() => setRevision((n) => n + 1), []);
  useEffect(() => {
    if (isExtension) {
      const applyState = (next: RuntimeState) => {
        setState(next);
        setConfig((previous) =>
          previous.url === next.config.url &&
          previous.token === next.config.token
            ? previous
            : next.config,
        );
      };
      runtime({ type: "ui.state" })
        .then(applyState)
        .finally(() => setLoading(false));
      const heartbeat = setInterval(
        () =>
          void runtime({ type: "ui.state" })
            .then(applyState)
            .catch(() => {}),
        2000,
      );
      const listener = (message: any) => {
        if (message.type === "server.event") {
          refresh();
          void runtime({ type: "ui.state" })
            .then(applyState)
            .catch(() => {});
        } else if (message.type === "transport.error") setNotice(message.error);
        else if (message.type === "transport.status")
          setState((s) =>
            s ? { ...s, connected: message.status === "connected" } : s,
          );
        else if (message.type === "capture.timing")
          void runtime({ type: "ui.state" })
            .then(applyState)
            .catch(() => {});
      };
      chrome.runtime.onMessage.addListener(listener);
      return () => {
        clearInterval(heartbeat);
        chrome.runtime.onMessage.removeListener(listener);
      };
    } else {
      try {
        setConfig(
          JSON.parse(sessionStorage.getItem("meet-local-config") || "null") || {
            url: "http://127.0.0.1:8765",
            token: "",
          },
        );
      } catch {}
      setLoading(false);
    }
  }, [refresh]);
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(""), 6500);
      return () => clearTimeout(timer);
    }
  }, [notice]);
  const api = useCallback<API>(
    async (path, method = "GET", body, asText = false) => {
      const response = await fetch(config.url + path, {
        method,
        headers: {
          Authorization: "Bearer " + config.token,
          "Content-Type": "application/json",
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!response.ok) {
        const data = await response
          .json()
          .catch(() => ({ message: "Không thể đọc phản hồi backend" }));
        throw new APIError(
          response.status,
          data.code,
          response.status === 401
            ? "Pairing token đã hết hiệu lực. Nhập token mới trong Cài đặt."
            : data.message || `HTTP ${response.status}`,
          data,
        );
      }
      return asText ? response.text() : response.json();
    },
    [config.url, config.token],
  );
  async function saveConfig(next: LocalConfig) {
    const url = new URL(next.url);
    if (
      url.protocol !== "http:" ||
      !["localhost", "127.0.0.1"].includes(url.hostname) ||
      url.port !== "8765"
    )
      throw new Error("Chỉ hỗ trợ backend loopback cổng 8765");
    next = { url: url.origin, token: next.token.trim() };
    if (isExtension) await runtime({ type: "ui.config", config: next });
    else sessionStorage.setItem("meet-local-config", JSON.stringify(next));
    setConfig(next);
    refresh();
  }
  return (
    <AppContext.Provider
      value={{
        api,
        config,
        state,
        loading,
        revision,
        refresh,
        saveConfig,
        toast: setNotice,
      }}
    >
      {children}
      {notice && (
        <div role="status" className="toast">
          {notice}
        </div>
      )}
    </AppContext.Provider>
  );
}
export const useApp = () => useContext(AppContext);
export function useLoad<T>(path: string | null, extra = 0) {
  const { api, revision } = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!path) {
      setLoading(false);
      setData(null);
      return;
    }
    let alive = true;
    setLoading(true);
    api<T>(path)
      .then((value) => {
        if (alive) {
          setData(value);
          setError("");
        }
      })
      .catch((e) => {
        if (alive) {
          setError(e.message);
          if (e.status === 404) setData(null);
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [path, api, revision, extra]);
  return { data, error, loading, setData };
}
export const navigate = (route: string) => {
  location.hash = route;
};
export function useRoute() {
  const [route, setRoute] = useState(location.hash.slice(1) || "/projects");
  useEffect(() => {
    const fn = () => setRoute(location.hash.slice(1) || "/projects");
    addEventListener("hashchange", fn);
    return () => removeEventListener("hashchange", fn);
  }, []);
  return route;
}
