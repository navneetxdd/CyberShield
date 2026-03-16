import { useState, useEffect, useCallback, useRef } from 'react';
import { CONFIG } from '../lib/config';

export function useBackendStream(cameraId: string) {
  const [data, setData] = useState<any>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    if (!cameraId) {
      setConnected(false);
      setError(null);
      return;
    }
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${CONFIG.WS_URL}/ws/analytics/${cameraId}?api_key=${CONFIG.API_KEY}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log(`WebSocket connected: ${cameraId}`);
      setConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        setData(payload);
      } catch (e) {
        console.error("Failed to parse WS message", e);
      }
    };

    ws.onerror = () => {
      setError("WebSocket connection error");
    };

    ws.onclose = () => {
      setConnected(false);
      console.log(`WebSocket closed: ${cameraId}. Reconnecting...`);
      reconnectTimeoutRef.current = window.setTimeout(connect, 3000);
    };

    wsRef.current = ws;
  }, [cameraId]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on intentional close
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { data, connected, error };
}
