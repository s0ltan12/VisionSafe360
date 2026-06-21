import { useCallback, useEffect, useRef, useState } from 'react';
import { WS_BASE_URL, getAuthToken } from '../api';

export type RealtimeStatus = 'live' | 'reconnecting' | 'offline';

type RealtimeSocketOptions = {
  path: string;
  enabled?: boolean;
  onEvent: (payload: any) => void;
};

export function useRealtimeSocket({ path, enabled = true, onEvent }: RealtimeSocketOptions) {
  const [status, setStatus] = useState<RealtimeStatus>('offline');
  const [lastEventAt, setLastEventAt] = useState<string | null>(null);
  const eventHandlerRef = useRef(onEvent);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(false);

  useEffect(() => {
    eventHandlerRef.current = onEvent;
  }, [onEvent]);

  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false;
    if (reconnectRef.current !== null) {
      window.clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('offline');
  }, []);

  useEffect(() => {
    if (!enabled) {
      disconnect();
      return undefined;
    }

    const token = getAuthToken();
    if (!token) {
      setStatus('offline');
      return undefined;
    }

    shouldReconnectRef.current = true;

    const connect = () => {
      if (!shouldReconnectRef.current) return;
      setStatus(reconnectAttemptsRef.current > 0 ? 'reconnecting' : 'offline');

      const separator = path.includes('?') ? '&' : '?';
      const ws = new WebSocket(`${WS_BASE_URL}${path}${separator}token=${encodeURIComponent(token)}`);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0;
        setStatus('live');
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'keepalive' || payload.type === 'connected' || payload.type === 'pong') {
            return;
          }
          setLastEventAt(new Date().toISOString());
          eventHandlerRef.current(payload);
        } catch {
          // Ignore malformed websocket messages.
        }
      };

      ws.onerror = () => {
        setStatus('reconnecting');
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (!shouldReconnectRef.current) {
          setStatus('offline');
          return;
        }
        reconnectAttemptsRef.current += 1;
        setStatus('reconnecting');
        const delay = Math.min(30000, 1000 * 2 ** Math.min(reconnectAttemptsRef.current, 5));
        reconnectRef.current = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      disconnect();
    };
  }, [disconnect, enabled, path]);

  return { status, lastEventAt, disconnect };
}
