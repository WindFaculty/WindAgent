/**
 * Sanctioned raw-socket boundary for the @windagent/realtime package.
 *
 * The Phase 11 architecture invariant ("zero direct feature websockets")
 * requires every feature-level realtime consumer to route through this
 * package. Feature code injects or imports this factory instead of
 * instantiating `WebSocket` directly, keeping the single instantiation site
 * inside the packages layer.
 */
export function createWebSocket(url: string, protocols?: string | string[]): WebSocket {
  return new WebSocket(url, protocols);
}
