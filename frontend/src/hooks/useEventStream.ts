import { useEffect, useRef, useState } from "react";
import { SSE_STREAM_URL } from "../services/api";
import type {
  NewEventPayload,
  ScraperFailurePayload,
  ScraperHealedPayload,
} from "../types";

export type StreamHandlers = {
  onNew?: (payload: NewEventPayload) => void;
  onAlert?: (payload: NewEventPayload) => void;
  onScraperFailure?: (payload: ScraperFailurePayload) => void;
  onHealed?: (payload: ScraperHealedPayload) => void;
};

export type StreamStatus = "connecting" | "connected" | "error";

/**
 * Subscribes to the backend SSE stream (GET /api/stream).
 * Handlers live in a ref so they can change without reconnecting.
 * EventSource reconnects automatically; we surface the status for UI.
 */
export function useEventStream(handlers: StreamHandlers) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);

  useEffect(() => {
    let es: EventSource | null = null;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      es = new EventSource(SSE_STREAM_URL);

      es.onopen = () => setStatus("connected");
      es.onerror = () => setStatus("error");

      es.addEventListener("new", (e) => {
        setStatus("connected");
        setLastMessageAt(Date.now());
        try {
          handlersRef.current.onNew?.(JSON.parse((e as MessageEvent).data));
        } catch {
          /* malformed payload — ignore */
        }
      });

      es.addEventListener("alerts", (e) => {
        setStatus("connected");
        setLastMessageAt(Date.now());
        try {
          handlersRef.current.onAlert?.(JSON.parse((e as MessageEvent).data));
        } catch {
          /* ignore */
        }
      });

      es.addEventListener("scrapers", (e) => {
        setLastMessageAt(Date.now());
        try {
          handlersRef.current.onScraperFailure?.(
            JSON.parse((e as MessageEvent).data),
          );
        } catch {
          /* ignore */
        }
      });

      es.addEventListener("healed", (e) => {
        setLastMessageAt(Date.now());
        try {
          handlersRef.current.onHealed?.(JSON.parse((e as MessageEvent).data));
        } catch {
          /* ignore */
        }
      });
    };

    connect();
    return () => {
      disposed = true;
      es?.close();
    };
  }, []);

  return { status, lastMessageAt };
}
