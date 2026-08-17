/**
 * useSystemMetrics Hook (Phase 6).
 * Manages real-time hardware telemetry via WebSocket with graceful HTTP polling fallback.
 * Strictly zero fake/synthetic numbers.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import type { SystemMetrics } from '@windagent/api-contracts';
import { useApiClient } from '../../../api/ApiProvider';
import type { SystemMetricHistory } from '../model/types';

const MAX_HISTORY_POINTS = 10;

export function useSystemMetrics(pollIntervalMs: number = 3000) {
  const apiClient = useApiClient();
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [history, setHistory] = useState<SystemMetricHistory>({
    cpu: [],
    ram: [],
    gpu: [],
    vram: [],
  });
  const [isRealtime, setIsRealtime] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isError, setIsError] = useState<boolean>(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<any>(null);
  const fallbackTimerRef = useRef<any>(null);

  const pushHistorySample = useCallback((m: SystemMetrics) => {
    setHistory((prev) => {
      const cpuVal = Math.round(m.cpu.usage_percent);
      const ramVal = Math.round(m.memory.usage_percent);
      const gpuVal = m.gpu.length > 0 ? Math.round(m.gpu[0].utilization_percent) : 0;
      const vramVal =
        m.gpu.length > 0 && m.gpu[0].memory_total_bytes > 0
          ? Math.round((m.gpu[0].memory_used_bytes / m.gpu[0].memory_total_bytes) * 100)
          : 0;

      return {
        cpu: [...prev.cpu.slice(-(MAX_HISTORY_POINTS - 1)), cpuVal],
        ram: [...prev.ram.slice(-(MAX_HISTORY_POINTS - 1)), ramVal],
        gpu: [...prev.gpu.slice(-(MAX_HISTORY_POINTS - 1)), gpuVal],
        vram: [...prev.vram.slice(-(MAX_HISTORY_POINTS - 1)), vramVal],
      };
    });
  }, []);

  const fetchHttpSnapshot = useCallback(async () => {
    try {
      const data = await apiClient.system.getMetrics();
      setMetrics(data);
      pushHistorySample(data);
      setIsLoading(false);
      setIsError(false);
    } catch {
      setIsError(true);
      setIsLoading(false);
    }
  }, [apiClient, pushHistorySample]);

  useEffect(() => {
    let unmounted = false;

    const connectWebSocket = () => {
      if (unmounted) return;

      try {
        const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = typeof window !== 'undefined' && window.location.host ? window.location.host : 'localhost:8000';
        const wsUrl = `${protocol}//${host}/ws/v3/system/metrics`;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!unmounted) {
            setIsRealtime(true);
            setIsError(false);
          }
        };

        ws.onmessage = (event) => {
          if (unmounted) return;
          try {
            const data = JSON.parse(event.data);
            if (data?.payload) {
              const m = data.payload as SystemMetrics;
              setMetrics(m);
              pushHistorySample(m);
              setIsLoading(false);
            }
          } catch {
            // ignore malformed message
          }
        };

        ws.onerror = () => {
          if (!unmounted) {
            setIsRealtime(false);
          }
        };

        ws.onclose = () => {
          if (!unmounted) {
            setIsRealtime(false);
            // Attempt reconnect in 3s
            reconnectTimerRef.current = setTimeout(connectWebSocket, 3000);
          }
        };
      } catch {
        if (!unmounted) {
          setIsRealtime(false);
        }
      }
    };

    // Initial HTTP snapshot for immediate rendering
    fetchHttpSnapshot();

    // Start WebSocket
    connectWebSocket();

    // Start polling fallback in case WebSocket is disconnected
    fallbackTimerRef.current = setInterval(() => {
      if (!isRealtime) {
        fetchHttpSnapshot();
      }
    }, pollIntervalMs);

    return () => {
      unmounted = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (fallbackTimerRef.current) clearInterval(fallbackTimerRef.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [fetchHttpSnapshot, isRealtime, pollIntervalMs]);

  return {
    metrics,
    history,
    isRealtime,
    isLoading,
    isError,
    refetch: fetchHttpSnapshot,
  };
}
