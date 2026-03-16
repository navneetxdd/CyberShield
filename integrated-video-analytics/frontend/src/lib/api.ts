import { getConfig } from "./config";

function buildUrl(path: string): string {
  const config = getConfig();
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return `${config.API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export function apiAssetUrl(path: string | null | undefined): string {
  const value = String(path || "").trim();
  if (!value) {
    return "";
  }
  const config = getConfig();
  const resolved = /^https?:\/\//i.test(value)
    ? new URL(value)
    : new URL(value.startsWith("/") ? `${config.API_URL}${value}` : `${config.API_URL}/${value}`);
  if (config.API_KEY && !resolved.searchParams.has("api_key")) {
    resolved.searchParams.set("api_key", config.API_KEY);
  }
  return resolved.toString();
}

function withApiKey(headers?: HeadersInit): Headers {
  const config = getConfig();
  const resolved = new Headers(headers || {});
  if (config.API_KEY && !resolved.has("X-API-Key")) {
    resolved.set("X-API-Key", config.API_KEY);
  }
  return resolved;
}

export async function apiFetch<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const requestOptions: RequestInit = {
    ...options,
    headers: withApiKey(options.headers),
  };

  const response = await fetch(buildUrl(path), requestOptions);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as T;
}

export async function apiUpload<T = unknown>(path: string, payload: File | FormData): Promise<T> {
  const form = payload instanceof FormData ? payload : (() => {
    const next = new FormData();
    next.append("file", payload);
    return next;
  })();

  const response = await fetch(buildUrl(path), {
    method: "POST",
    body: form,
    headers: withApiKey(),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return (await response.json()) as T;
}
