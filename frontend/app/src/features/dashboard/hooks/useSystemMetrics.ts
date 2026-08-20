/**
 * useSystemMetrics Hook (Phase 6 & 11).
 * Manages real-time hardware telemetry via @windagent/realtime with graceful HTTP polling fallback.
 * Strictly zero fake/synthetic numbers.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import type { SystemMetrics } from '@windagent/api-contracts';
import { useApiClient } from '../../../api/ApiProvider';
import { useRealtimeClient } from '../../../realtime/RealtimeProvider';
import type { SystemMetricHistory } from '../model/types';

const MAX_HISTORY_POINTS = 10;

export function useSystemMetrics(pollIntervalMs: number = 3000) {
  const apiClient = useApiClient();
  const realtime = useRealtimeClient();
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [history, setHistory] = useState<SystemMetricHistory>({
    cpu: [],
    ram: [],
    gpu: [],
    vram: [],
  });
  const [isRealtime, setIsRealtime] = useState<boolean>(realtime.getState() === 'CONNECTED');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isError, setIsError] = useState<boolean>(false);

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
    // Initial HTTP snapshot for immediate rendering
    fetchHttpSnapshot();

    const unsubState = realtime.onStateChange((state) => {
      setIsRealtime(state === 'CONNECTED');
    });

    const unsubEvents = realtime.subscribe<SystemMetrics>(
      { aggregateType: 'system_metrics' },
      (envelope) => {
        if (envelope?.payload) {
          const m = envelope.payload as unknown as SystemMetrics;
          setMetrics(m);
          pushHistorySample(m);
          setIsLoading(false);
        }
      }
    );

    // Start polling fallback in case WebSocket is disconnected or degraded
    fallbackTimerRef.current = setInterval(() => {
      if (realtime.getState() !== 'CONNECTED') {
        fetchHttpSnapshot();
      }
    }, pollIntervalMs);

    return () => {
      unsubState();
      unsubEvents();
      if (fallbackTimerRef.current) clearInterval(fallbackTimerRef.current);
    };
  }, [fetchHttpSnapshot, realtime, pollIntervalMs, pushHistorySample]);

  return {
    metrics,
    history,
    isRealtime,
    isLoading,
    isError,
    refetch: fetchHttpSnapshot,
  };
}
