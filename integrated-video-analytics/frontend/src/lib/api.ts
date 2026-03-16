import { CONFIG } from "./config";

function buildUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return `${CONFIG.API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

function withApiKey(headers?: HeadersInit): Headers {
  const resolved = new Headers(headers || {});
  if (CONFIG.API_KEY && !resolved.has("X-API-Key")) {
    resolved.set("X-API-Key", CONFIG.API_KEY);
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
