const browserOrigin = typeof window !== "undefined" ? window.location.origin : "http://localhost:8080";

const wsOrigin =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
    : "ws://localhost:8080";

export const CONFIG = {
  API_URL: (import.meta.env.VITE_API_URL || browserOrigin).replace(/\/$/, ""),
  WS_URL: (import.meta.env.VITE_WS_URL || wsOrigin).replace(/\/$/, ""),
  API_KEY: import.meta.env.VITE_API_KEY || "",
} as const;
