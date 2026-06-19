/** Subscribe to a session's WebSocket event stream.

 * The hook owns the lifecycle of the WsHandle: opens on mount / sessionId
 * change, dispatches events into the parent reducer, closes on unmount.
 */

import { useEffect, useRef } from "react";

import { connectWs, type WsHandle } from "../api/client";
import type { EventEnvelope } from "../api/types";

type EventHandler = (env: EventEnvelope) => void;
type CloseHandler = (reason: string) => void;

export interface UseSessionEventsOptions {
  onEvent: EventHandler;
  onClose?: CloseHandler;
}

export function useSessionEvents(
  sessionId: string | null,
  options: UseSessionEventsOptions,
): void {
  const handleRef = useRef<WsHandle | null>(null);
  // Keep latest handlers without re-running the effect.
  const onEventRef = useRef(options.onEvent);
  const onCloseRef = useRef(options.onClose);
  onEventRef.current = options.onEvent;
  onCloseRef.current = options.onClose;

  useEffect(() => {
    if (!sessionId) {
      handleRef.current?.close();
      handleRef.current = null;
      return;
    }
    const handle = connectWs(sessionId, {
      onEvent: (env) => onEventRef.current(env),
      onClose: (reason) => onCloseRef.current?.(reason),
    });
    handleRef.current = handle;
    return () => {
      handle.close();
      handleRef.current = null;
    };
  }, [sessionId]);
}