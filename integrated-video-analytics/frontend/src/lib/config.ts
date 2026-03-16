export interface RuntimeConfig {
  API_URL: string;
  WS_URL: string;
  API_KEY: string;
}

const STORAGE_KEY = "cybershield.runtime_config";
const browserOrigin = typeof window !== "undefined" ? window.location.origin : "http://localhost:8080";
const defaultApiUrl = (import.meta.env.VITE_API_URL || browserOrigin).replace(/\/$/, "");
const defaultWsUrl = (
  import.meta.env.VITE_WS_URL
  || (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
    : "ws://localhost:8080")
).replace(/\/$/, "");

function normalizeUrl(value: string, fallback: string): string {
  const trimmed = String(value || "").trim().replace(/\/$/, "");
  return trimmed || fallback;
}

function deriveWsUrl(apiUrl: string): string {
  if (/^wss?:\/\//i.test(apiUrl)) {
    return apiUrl.replace(/^http/i, "ws");
  }
  if (/^https?:\/\//i.test(apiUrl)) {
    return apiUrl.replace(/^http/i, "ws");
  }
  return defaultWsUrl;
}

export function getConfig(): RuntimeConfig {
  if (typeof window === "undefined") {
    return {
      API_URL: defaultApiUrl,
      WS_URL: defaultWsUrl,
      API_KEY: import.meta.env.VITE_API_KEY || "",
    };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {
        API_URL: defaultApiUrl,
        WS_URL: defaultWsUrl,
        API_KEY: import.meta.env.VITE_API_KEY || "",
      };
    }
    const parsed = JSON.parse(raw) as Partial<RuntimeConfig>;
    const apiUrl = normalizeUrl(parsed.API_URL || defaultApiUrl, defaultApiUrl);
    return {
      API_URL: apiUrl,
      WS_URL: normalizeUrl(parsed.WS_URL || deriveWsUrl(apiUrl), deriveWsUrl(apiUrl)),
      API_KEY: String(parsed.API_KEY || ""),
    };
  } catch {
    return {
      API_URL: defaultApiUrl,
      WS_URL: defaultWsUrl,
      API_KEY: import.meta.env.VITE_API_KEY || "",
    };
  }
}

export function updateConfig(next: Partial<RuntimeConfig>): RuntimeConfig {
  const current = getConfig();
  const apiUrl = normalizeUrl(next.API_URL ?? current.API_URL, defaultApiUrl);
  const resolved: RuntimeConfig = {
    API_URL: apiUrl,
    WS_URL: normalizeUrl(next.WS_URL ?? deriveWsUrl(apiUrl), deriveWsUrl(apiUrl)),
    API_KEY: String(next.API_KEY ?? current.API_KEY ?? ""),
  };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(resolved));
    window.dispatchEvent(new CustomEvent("cybershield-config-updated", { detail: resolved }));
  }
  return resolved;
}

export const CONFIG = {
  get API_URL() {
    return getConfig().API_URL;
  },
  get WS_URL() {
    return getConfig().WS_URL;
  },
  get API_KEY() {
    return getConfig().API_KEY;
  },
};
