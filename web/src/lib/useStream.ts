"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { API_BASE } from "./api";
import type { TypedStreamMessage } from "./types";

const EVENT_TYPES = [
  "hello",
  "reading",
  "risk",
  "event",
  "checkin",
  "checkin_update",
  "chat",
  "emergency",
  "buddy_nudge",
  "buddy_ack",
  "community",
];

export interface UseStreamOptions {
  userId?: string | string[];
  community?: boolean;
  enabled?: boolean;
  onMessage?: (message: TypedStreamMessage) => void;
}

export interface UseStreamResult {
  connected: boolean;
  connecting: boolean;
  error: Error | null;
  lastMessage: TypedStreamMessage | null;
}

export function useStream(options: UseStreamOptions = {}): UseStreamResult {
  const { userId = "maya", community = false, enabled = true, onMessage } = options;

  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [lastMessage, setLastMessage] = useState<TypedStreamMessage | null>(null);

  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const esRef = useRef<EventSource | null>(null);

  const handleRawMessage = useCallback((type: string, rawData: string) => {
    try {
      const parsed = JSON.parse(rawData);
      // Backend format is { type, topic, ts, data } (except hello which has { topics })
      const message = {
        type: (parsed.type || type) as string,
        topic: parsed.topic || "",
        ts: parsed.ts ?? Date.now() / 1000,
        data: parsed.data !== undefined ? parsed.data : parsed,
      } as TypedStreamMessage;

      setLastMessage(message);
      if (onMessageRef.current) {
        onMessageRef.current(message);
      }
    } catch (err) {
      console.warn("[useStream] Failed to parse SSE message:", rawData, err);
    }
  }, []);

  const serializedUserIds = Array.isArray(userId) ? userId.join(",") : userId;

  useEffect(() => {
    if (!enabled || typeof window === "undefined") {
      return;
    }

    const uids = serializedUserIds ? serializedUserIds.split(",").filter(Boolean) : [];
    const search = new URLSearchParams();
    for (const uid of uids) {
      search.append("user_id", uid);
    }
    if (community) {
      search.set("community", "true");
    }

    const qs = search.toString();
    const url = `${API_BASE}/api/stream${qs ? `?${qs}` : ""}`;

    let isCancelled = false;

    if (esRef.current) {
      esRef.current.close();
    }

    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      if (isCancelled) return;
      setConnected(true);
      setError(null);
    };

    es.onerror = () => {
      if (isCancelled) return;
      setConnected(false);
      setError(new Error("SSE connection error"));
    };

    es.onmessage = (event) => {
      if (isCancelled) return;
      handleRawMessage("message", event.data);
    };

    for (const eventType of EVENT_TYPES) {
      es.addEventListener(eventType, (event: MessageEvent) => {
        if (isCancelled) return;
        handleRawMessage(eventType, event.data);
      });
    }

    return () => {
      isCancelled = true;
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      setConnected(false);
    };
  }, [enabled, community, serializedUserIds, handleRawMessage]);

  const connecting = enabled && !connected && !error;

  return { connected, connecting, error, lastMessage };
}
