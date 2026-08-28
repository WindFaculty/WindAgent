/**
 * LogsPage — Runtime Logs (real-data edition).
 * All metrics, histogram and detail are derived purely from /api/v3/logs
 * (LogService ring-buffer) and the live WebSocket stream. No synthetic
 * fallbacks, mock spark arrays or fabricated defaults.
 */
import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import {
  Activity,
  Search,
  Pause,
  Play,
  Download,
  Trash2,
  Copy,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Filter,
  Maximize2,
  X,
  Eye,
} from 'lucide-react';
import { useLogs, useLogStream, useLogSources, LOG_LEVELS } from '../hooks/useLogs';
import { useRealtimeClient } from '../../../realtime/RealtimeProvider';
import type { LogRecord } from '@windagent/api-contracts';

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------
const LEVEL_LABEL: Record<string, string> = {
  DEBUG: 'DEBUG',
  INFO: 'INFO',
  WARNING: 'WARN',
  WARN: 'WARN',
  ERROR: 'ERROR',
  CRITICAL: 'CRITICAL',
};

const LEVEL_STYLE: Record<string, { bg: string; fg: string; border: string }> = {
  DEBUG: { bg: 'rgba(140,144,159,0.14)', fg: '#9aa0b3', border: 'rgba(140,144,159,0.25)' },
  INFO: { bg: 'rgba(77,142,255,0.14)', fg: '#60a5fa', border: 'rgba(77,142,255,0.28)' },
  WARNING: { bg: 'rgba(245,158,11,0.14)', fg: '#fbbf24', border: 'rgba(245,158,11,0.32)' },
  WARN: { bg: 'rgba(245,158,11,0.14)', fg: '#fbbf24', border: 'rgba(245,158,11,0.32)' },
  ERROR: { bg: 'rgba(239,68,68,0.14)', fg: '#f87171', border: 'rgba(239,68,68,0.30)' },
  CRITICAL: { bg: 'rgba(239,68,68,0.22)', fg: '#ffb4ab', border: 'rgba(239,68,68,0.40)' },
};

function fmtTime(ts?: string | null): string {
  if (!ts) return '--:--:--.---';
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return String(ts).slice(11, 23);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    const ms = String(d.getMilliseconds()).padStart(3, '0');
    return `${hh}:${mm}:${ss}.${ms}`;
  } catch {
    return String(ts).slice(11, 23);
  }
}

function fmtNumber(n: number): string {
  return n.toLocaleString('vi-VN');
}

function sparkPath(values: number[], w = 68, h = 24): string {
  if (values.length < 2) return `M0 ${h / 2} L${w} ${h / 2}`;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = w / (values.length - 1);
  return values
    .map((v, i) => {
      const x = i * step;
      const y = h - ((v - min) / span) * (h - 4) - 2;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
}

function calcP95(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.ceil(0.95 * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(idx, sorted.length - 1))];
}

function calcTrend(current: number, previous: number): number | null {
  if (previous === 0) {
    if (current === 0) return 0;
    return null; // not enough history – hide delta
  }
  return ((current - previous) / previous) * 100;
}

function formatDelta(pct: number | null): { text: string; color: string; up: boolean } | null {
  if (pct === null || !Number.isFinite(pct)) return null;
  if (Math.abs(pct) < 0.05) return { text: '0% so với kỳ trước', color: 'var(--text-dim, #8c909f)', up: false };
  const up = pct > 0;
  const color = pct > 0 ? '#f87171' : '#4edea3'; // up = more logs = warning red, down = green
  // for error/warning, up is bad (red), for total, up is neutral blue – caller overrides if needed
  return { text: `${Math.abs(pct).toFixed(1)}% so với kỳ trước`, color, up };
}

function relativeTime(ts?: string | null): string {
  if (!ts) return '—';
  const t = new Date(ts).getTime();
  if (!Number.isFinite(t)) return '—';
  const diff = Date.now() - t;
  if (diff < 0) return 'vừa xong';
  if (diff < 1000) return `${diff}ms trước`;
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s trước`;
  if (diff < 3600_000) return `${Math.floor(diff / 60000)} phút trước`;
  if (diff < 86400_000) return `${Math.floor(diff / 3600000)} giờ trước`;
  return new Date(ts).toLocaleString('vi-VN');
}

// ------------------------------------------------------------------
// Main page
// ------------------------------------------------------------------
export const LogsPage: React.FC = () => {
  const [level, setLevel] = useState('');
  const [source, setSource] = useState('');
  const [agentFilter, setAgentFilter] = useState('');
  const [timeWindow, setTimeWindow] = useState<'15m' | '1h' | '24h' | 'all'>('15m');
  const [statusFilter, setStatusFilter] = useState<'Live' | 'Errors' | 'Warnings' | 'All'>('Live');
  const [search, setSearch] = useState('');
  const [live, setLive] = useState<LogRecord[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [showDetail, setShowDetail] = useState(true);
  const [metaExpanded, setMetaExpanded] = useState(true);
  const [payloadExpanded, setPayloadExpanded] = useState(true);

  const pageSizeOptions = [25, 50, 100] as const;

  // Real API: request the full ring-buffer (limit 1000 = server max) so
  // client-side metrics reflect the true runtime state.
  const { data: logs = [], isLoading, error } = useLogs({
    level: level || undefined,
    source: source || undefined,
    limit: 1000,
  });
  const { data: sources = [] } = useLogSources();

  // Track real WebSocket connection state
  const realtime = useRealtimeClient();
  const [wsState, setWsState] = useState(realtime.getState());
  useEffect(() => realtime.onStateChange(setWsState), [realtime]);
  const isWsLive = wsState === 'CONNECTED';

  // Live stream – only real envelopes, paused locally if user hits Pause
  useLogStream(
    useCallback(
      (record: LogRecord) => {
        if (isPaused) return;
        setLive((prev) => [record, ...prev].slice(0, 400));
      },
      [isPaused],
    ),
  );

  // Merge live + REST, dedup by timestamp|trace|message – all real records
  const merged = useMemo(() => {
    const out: LogRecord[] = [...live];
    const seen = new Set(out.map((r) => `${r.timestamp}|${r.message}|${r.trace_id ?? ''}`));
    for (const r of logs) {
      const k = `${r.timestamp}|${r.message}|${r.trace_id ?? ''}`;
      if (!seen.has(k)) {
        out.push(r);
        seen.add(k);
      }
    }
    // sort newest first by timestamp (real ordering)
    out.sort((a, b) => {
      const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
      const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
      return tb - ta;
    });
    return out;
  }, [live, logs]);

  // Distinct agent/run/task values derived from real records
  const agentOptions = useMemo(() => {
    const s = new Set<string>();
    for (const r of merged) {
      if (r.agent_instance_id) s.add(r.agent_instance_id);
      if (r.conversation_id) s.add(r.conversation_id);
      if (r.task_id) s.add(r.task_id);
    }
    return Array.from(s).slice(0, 40);
  }, [merged]);

  // Filtering – purely client-side on top of server-filtered list
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const now = Date.now();
    const winMs =
      timeWindow === '15m' ? 15 * 60 * 1000 : timeWindow === '1h' ? 60 * 60 * 1000 : timeWindow === '24h' ? 24 * 60 * 60 * 1000 : 0;

    return merged.filter((r) => {
      if (level && (r.level ?? '').toUpperCase() !== level.toUpperCase() && !(level === 'WARNING' && (r.level as string) === 'WARN')) return false;
      if (source && r.source !== source) return false;
      if (agentFilter) {
        const hay = `${r.agent_instance_id ?? ''} ${r.conversation_id ?? ''} ${r.task_id ?? ''} ${r.correlation_id ?? ''}`.toLowerCase();
        if (!hay.includes(agentFilter.toLowerCase())) return false;
      }
      if (statusFilter === 'Errors' && !['ERROR', 'CRITICAL'].includes((r.level ?? '').toUpperCase())) return false;
      if (statusFilter === 'Warnings' && !['WARNING', 'WARN'].includes((r.level ?? '').toUpperCase())) return false;
      if (q) {
        const hay = `${r.message} ${r.source} ${r.level} ${r.trace_id ?? ''} ${r.correlation_id ?? ''} ${JSON.stringify(r.metadata ?? {})}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (winMs) {
        const t = r.timestamp ? new Date(r.timestamp).getTime() : 0;
        if (t && now - t > winMs) return false;
      }
      return true;
    });
  }, [merged, level, source, agentFilter, statusFilter, search, timeWindow]);

  useEffect(() => {
    setPage(1);
  }, [level, source, agentFilter, statusFilter, search, timeWindow]);

  // ----------------------------------------------------------------
  // Histogram buckets — single source of truth for chart + sparklines
  // ----------------------------------------------------------------
  const histogram = useMemo(() => {
    if (filtered.length === 0) {
      return {
        buckets: [] as {
          label: string;
          start: number;
          count: number;
          errorCount: number;
          warnCount: number;
          distinctSources: Set<string>;
        }[],
        max: 1,
        p95: 0,
        perMinAvg: 0,
      };
    }
    const now = Date.now();
    // Use window-appropriate bucket size: 15m => 1m buckets, 1h => 5m, 24h => 60m
    let bucketMs: number;
    let bucketCount: number;
    if (timeWindow === '15m') {
      bucketMs = 60 * 1000;
      bucketCount = 15;
    } else if (timeWindow === '1h') {
      bucketMs = 5 * 60 * 1000;
      bucketCount = 12;
    } else if (timeWindow === '24h') {
      bucketMs = 60 * 60 * 1000;
      bucketCount = 24;
    } else {
      // 'all' – cover span of real data
      const times = filtered.map((r) => (r.timestamp ? new Date(r.timestamp).getTime() : 0)).filter(Boolean);
      const span = times.length ? Math.max(...times) - Math.min(...times) : 60 * 60 * 1000;
      bucketCount = 16;
      bucketMs = Math.max(60 * 1000, Math.ceil(span / bucketCount));
    }

    const buckets = Array.from({ length: bucketCount }, (_, i) => {
      const start = now - (bucketCount - 1 - i) * bucketMs;
      const d = new Date(start);
      const label =
        bucketMs >= 60 * 60 * 1000
          ? `${String(d.getHours()).padStart(2, '0')}h`
          : `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
      return { label, start, count: 0, errorCount: 0, warnCount: 0, distinctSources: new Set<string>() as Set<string> };
    });

    const windowStart = now - (bucketCount - 1) * bucketMs;
    for (const r of filtered) {
      const t = r.timestamp ? new Date(r.timestamp).getTime() : 0;
      if (!t || t < windowStart) {
        // for 'all', put oldest overflow into first bucket
        if (timeWindow === 'all' && t) buckets[0].count += 1;
        continue;
      }
      const idx = Math.min(bucketCount - 1, Math.floor((t - windowStart) / bucketMs));
      if (idx < 0) continue;
      const b = buckets[idx];
      b.count += 1;
      const lvl = (r.level ?? '').toUpperCase();
      if (lvl === 'ERROR' || lvl === 'CRITICAL') b.errorCount += 1;
      if (lvl === 'WARNING' || lvl === 'WARN') b.warnCount += 1;
      if (r.source) b.distinctSources.add(r.source);
    }
    const max = Math.max(1, ...buckets.map((b) => b.count));
    const counts = buckets.map((b) => b.count);
    const p95 = calcP95(counts);
    const perMinAvg = bucketMs === 0 ? 0 : filtered.length / (bucketCount * (bucketMs / 60000));
    return { buckets, max, p95, perMinAvg };
  }, [filtered, timeWindow]);

  // Sparks derived from real histogram (no mock)
  const sparks = useMemo(() => {
    const total = histogram.buckets.map((b) => b.count);
    const errors = histogram.buckets.map((b) => b.errorCount);
    const warnings = histogram.buckets.map((b) => b.warnCount);
    const sourcesTrend = histogram.buckets.map((b) => b.distinctSources.size);
    // per-min spark is same as total for now (both per-bucket rate)
    const perMin = total.map((c) => c);
    return { total, errors, warnings, sourcesTrend, perMin };
  }, [histogram.buckets]);

  // Metrics derived from real data only (no fallback 18 / 1842)
  const metrics = useMemo(() => {
    const now = new Date();
    const startOfToday = new Date(now);
    startOfToday.setHours(0, 0, 0, 0);
    const t0 = startOfToday.getTime();

    const todaySlice = merged.filter((r) => {
      const t = r.timestamp ? new Date(r.timestamp).getTime() : 0;
      return t >= t0;
    });
    // If no timestamp qualifies as today (e.g., stale buffer), fall back to full buffer
    const baseForToday = todaySlice.length > 0 || merged.length === 0 ? todaySlice : merged;

    const totalToday = baseForToday.length;
    const errToday = baseForToday.filter((r) => ['ERROR', 'CRITICAL'].includes((r.level ?? '').toUpperCase())).length;
    const warnToday = baseForToday.filter((r) => ['WARNING', 'WARN'].includes((r.level ?? '').toUpperCase())).length;
    const srcCount = new Set(merged.map((r) => r.source).filter(Boolean)).size;

    // p95 logs/min among buckets; avg logs/min over window
    const p95PerMin = histogram.p95;
    const avgPerMin = histogram.perMinAvg ? Math.round(histogram.perMinAvg) : 0;

    // Trends: split histogram in half (prev vs curr) for each metric
    const half = Math.floor(sparks.total.length / 2) || 1;
    const totalPrev = sparks.total.slice(0, half).reduce((a, b) => a + b, 0);
    const totalCurr = sparks.total.slice(half).reduce((a, b) => a + b, 0);
    const errPrev = sparks.errors.slice(0, half).reduce((a, b) => a + b, 0);
    const errCurr = sparks.errors.slice(half).reduce((a, b) => a + b, 0);
    const warnPrev = sparks.warnings.slice(0, half).reduce((a, b) => a + b, 0);
    const warnCurr = sparks.warnings.slice(half).reduce((a, b) => a + b, 0);

    return {
      totalToday,
      errToday,
      warnToday,
      srcCount,
      p95PerMin,
      avgPerMin,
      trends: {
        total: calcTrend(totalCurr, totalPrev),
        err: calcTrend(errCurr, errPrev),
        warn: calcTrend(warnCurr, warnPrev),
      },
    };
  }, [merged, histogram.p95, histogram.perMinAvg, sparks]);

  // Pagination (real)
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageSlice = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page, pageSize]);

  // Selection – real record only
  const selected = useMemo(() => {
    if (selectedKey) {
      const found = filtered.find((r) => `${r.timestamp}|${r.trace_id ?? ''}|${r.message}` === selectedKey);
      if (found) return found;
    }
    return filtered.find((r) => (r.level ?? '').toUpperCase() === 'ERROR') ?? filtered[0] ?? null;
  }, [filtered, selectedKey]);

  const tableWrapRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (autoScroll && tableWrapRef.current && !isPaused) {
      tableWrapRef.current.scrollTop = 0;
    }
  }, [filtered.length, autoScroll, isPaused]);

  const handleExport = useCallback(() => {
    if (filtered.length === 0) return;
    const blob = new Blob([JSON.stringify(filtered.slice(0, 1000), null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `windagent-logs-${new Date().toISOString().slice(0, 19)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [filtered]);

  const handleClear = useCallback(() => {
    setLive([]);
    setSelectedKey(null);
  }, []);

  const handleCopy = useCallback((txt: string) => {
    if (!txt || txt === '—') return;
    navigator.clipboard?.writeText(txt).catch(() => {});
  }, []);

  const [activeTab, setActiveTab] = useState<'Stream' | 'Traces' | 'Metrics' | 'Services' | 'Sources'>('Stream');

  // Label for window
  const windowLabel =
    timeWindow === '15m' ? '15 phút qua' : timeWindow === '1h' ? '1 giờ qua' : timeWindow === '24h' ? '24 giờ qua' : 'toàn bộ buffer';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
        padding: '16px 18px 14px 18px',
        minHeight: 0,
        background: 'var(--bg-darker, #060e20)',
        color: 'var(--text-main, #dae2fd)',
        fontFamily: 'var(--font-sans, system-ui, sans-serif)',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span
              style={{
                width: 28,
                height: 28,
                borderRadius: 8,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'rgba(77,142,255,0.14)',
                border: '1px solid rgba(77,142,255,0.22)',
                color: '#60a5fa',
              }}
            >
              <Activity size={16} />
            </span>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 800, letterSpacing: '-0.3px' }}>Runtime Logs</h2>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '2px 8px',
                borderRadius: 999,
                background: isPaused ? 'rgba(245,158,11,0.12)' : isWsLive ? 'rgba(78,222,163,0.10)' : 'rgba(239,68,68,0.10)',
                border: `1px solid ${isPaused ? 'rgba(245,158,11,0.28)' : isWsLive ? 'rgba(78,222,163,0.22)' : 'rgba(239,68,68,0.24)'}`,
                color: isPaused ? '#fbbf24' : isWsLive ? '#4edea3' : '#f87171',
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: 0.3,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: 'currentColor',
                  boxShadow: isPaused || !isWsLive ? 'none' : '0 0 6px currentColor',
                }}
              />
              {isPaused ? 'PAUSED' : isWsLive ? 'LIVE • WebSocket' : 'OFFLINE'}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-dim, #8c909f)' }}>
              {filtered.length.toLocaleString('vi-VN')} records
              {isLoading ? ' • đang tải…' : ''}
              {error ? ' • lỗi tải' : ''}
            </span>
          </div>
          <p style={{ margin: '6px 0 0 0', fontSize: 12.5, color: 'var(--text-muted, #c2c6d6)', opacity: 0.9 }}>
            Structured runtime records with correlation / trace IDs. Live stream over WebSocket.
            <span style={{ color: 'var(--text-dim, #8c909f)', marginLeft: 6 }}>Buffer: {merged.length.toLocaleString('vi-VN')} • {windowLabel}</span>
          </p>
        </div>
      </div>

      {/* Metric deck — 5 cards, all values from real API */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(5, minmax(0, 1fr))',
          gap: 10,
        }}
      >
        {(() => {
          const totalDelta = formatDelta(metrics.trends.total);
          // Override color: for total, up = neutral blue, not red
          if (totalDelta && metrics.trends.total !== null && metrics.trends.total > 0) totalDelta.color = '#60a5fa';
          if (totalDelta && metrics.trends.total !== null && metrics.trends.total < 0) totalDelta.color = '#4edea3';
          return (
            <MetricCard
              title="TỔNG LOGS HÔM NAY"
              value={fmtNumber(metrics.totalToday)}
              deltaText={totalDelta?.text ?? (sparks.total.length < 2 ? 'chưa đủ dữ liệu' : '0% so với kỳ trước')}
              deltaColor={totalDelta?.color ?? 'var(--text-dim, #8c909f)'}
              deltaUp={totalDelta?.up ?? false}
              sparkValues={sparks.total}
              sparkColor="#3b82f6"
            />
          );
        })()}
        {(() => {
          const d = formatDelta(metrics.trends.err);
          // errors: up = bad = red (already)
          return (
            <MetricCard
              title="ERRORS"
              value={fmtNumber(metrics.errToday)}
              deltaText={d?.text ?? (sparks.errors.length < 2 ? 'chưa đủ dữ liệu' : '0% so với kỳ trước')}
              deltaColor={d?.color ?? 'var(--text-dim, #8c909f)'}
              deltaUp={d?.up ?? false}
              sparkValues={sparks.errors}
              sparkColor="#ef4444"
            />
          );
        })()}
        {(() => {
          const d = formatDelta(metrics.trends.warn);
          return (
            <MetricCard
              title="WARNINGS"
              value={fmtNumber(metrics.warnToday)}
              deltaText={d?.text ?? (sparks.warnings.length < 2 ? 'chưa đủ dữ liệu' : '0% so với kỳ trước')}
              deltaColor={d?.color ?? 'var(--text-dim, #8c909f)'}
              deltaUp={d?.up ?? false}
              sparkValues={sparks.warnings}
              sparkColor="#f59e0b"
            />
          );
        })()}
        <MetricCard
          title="SOURCES ĐANG KẾT NỐI"
          value={fmtNumber(metrics.srcCount)}
          sub={isWsLive ? 'WebSocket • connected' : 'WebSocket • offline'}
          live={isWsLive}
          sparkValues={sparks.sourcesTrend}
          sparkColor="#10b981"
        />
        <MetricCard
          title="LOGS / PHÚT (P95)"
          value={fmtNumber(metrics.p95PerMin)}
          sub={`trung bình ${fmtNumber(metrics.avgPerMin)}/phút • ${windowLabel}`}
          sparkValues={sparks.perMin}
          sparkColor="#8b5cf6"
        />
      </div>

      {/* Filter bar – backed by real query params + client refinement */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
          background: 'var(--bg-panel, #131b2e)',
          border: '1px solid var(--border-color, #424754)',
          borderRadius: 10,
          padding: '8px 10px',
        }}
      >
        <div style={{ position: 'relative', flex: '0 1 280px', minWidth: 220 }}>
          <Search size={14} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-dim, #8c909f)' }} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Tìm kiếm logs..."
            style={{
              width: '100%',
              padding: '7px 44px 7px 30px',
              borderRadius: 8,
              border: '1px solid var(--border-color, #2a3347)',
              background: '#0b1220',
              color: 'var(--text-main, #dae2fd)',
              fontSize: 12.5,
              outline: 'none',
            }}
          />
          <span
            style={{
              position: 'absolute',
              right: 6,
              top: '50%',
              transform: 'translateY(-50%)',
              fontSize: 10,
              color: 'var(--text-dim, #8c909f)',
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 5,
              padding: '2px 5px',
              fontFamily: 'var(--font-mono, monospace)',
            }}
          >
            ⌘ K
          </span>
        </div>

        <FilterSelect label="Mức log" value={level} onChange={setLevel} options={['', ...LOG_LEVELS]} placeholder="Tất cả" />
        <FilterSelect label="Nguồn" value={source} onChange={setSource} options={['', ...sources]} placeholder="Tất cả" />
        <FilterSelect
          label="Agent / Run"
          value={agentFilter}
          onChange={setAgentFilter}
          options={['', ...agentOptions]}
          placeholder="Tất cả"
        />
        <FilterSelect
          label="Thời gian"
          value={timeWindow}
          onChange={(v) => setTimeWindow(v as typeof timeWindow)}
          options={['15m', '1h', '24h', 'all']}
          labels={{ '15m': '15 phút qua', '1h': '1 giờ qua', '24h': '24 giờ qua', all: 'Tất cả' }}
          placeholder="Thời gian"
        />
        <FilterSelect
          label="Trạng thái"
          value={statusFilter}
          onChange={(v) => setStatusFilter(v as typeof statusFilter)}
          options={['Live', 'Errors', 'Warnings', 'All']}
          labels={{ Live: 'Live', Errors: 'Chỉ lỗi', Warnings: 'Cảnh báo', All: 'Tất cả' }}
          placeholder="Trạng thái"
        />

        <div style={{ flex: 1 }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button onClick={() => setIsPaused((v) => !v)} style={toolbarBtnStyle()} title={isPaused ? 'Tiếp tục' : 'Tạm dừng'}>
            {isPaused ? <Play size={13} /> : <Pause size={13} />} {isPaused ? 'Resume' : 'Pause'}
          </button>
          <button
            onClick={() => setAutoScroll((v) => !v)}
            style={{
              ...toolbarBtnStyle(autoScroll),
              background: autoScroll ? 'rgba(77,142,255,0.16)' : 'transparent',
              borderColor: autoScroll ? 'rgba(77,142,255,0.32)' : 'var(--border-color, #424754)',
              color: autoScroll ? '#60a5fa' : 'var(--text-muted, #c2c6d6)',
            }}
          >
            <Eye size={13} /> Auto-scroll
          </button>
          <button onClick={handleExport} disabled={filtered.length === 0} style={toolbarBtnStyle(filtered.length > 0)}>
            <Download size={13} /> Export
          </button>
          <button onClick={handleClear} style={{ ...toolbarBtnStyle(), color: '#f87171', borderColor: 'rgba(239,68,68,0.30)' }}>
            <Trash2 size={13} /> Clear
          </button>
        </div>
      </div>

      {/* Main content */}
      <div style={{ display: 'flex', gap: 10, minHeight: 0, alignItems: 'stretch', flex: 1 }}>
        {/* Left stack */}
        <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0 }}>
          {/* Histogram panel – real data */}
          <div
            style={{
              background: 'var(--bg-panel, #131b2e)',
              border: '1px solid var(--border-color, #424754)',
              borderRadius: 10,
              padding: '10px 12px 8px 12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <div>
                <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: 0.6, color: 'var(--text-muted, #c2c6d6)', textTransform: 'uppercase' }}>
                  LƯỢNG LOGS THEO THỜI GIAN
                </div>
                <div style={{ fontSize: 11, color: '#60a5fa', fontWeight: 600, marginTop: 2 }}>
                  {histogram.buckets.length === 0 ? '—' : `${histogram.p95.toLocaleString('vi-VN')} logs/bucket (P95) • ${windowLabel}`}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-dim, #8c909f)', fontSize: 11 }}>
                <Clock3 size={12} /> {filtered.length.toLocaleString('vi-VN')} trong cửa sổ
              </div>
            </div>

            {histogram.buckets.length === 0 ? (
              <div style={{ height: 72, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim, #8c909f)', fontSize: 11, border: '1px dashed rgba(255,255,255,0.08)', borderRadius: 8 }}>
                Chưa có dữ liệu trong khoảng thời gian này
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 72, padding: '0 2px' }}>
                  {histogram.buckets.map((b, i) => {
                    const h = b.count === 0 ? 4 : Math.max(6, Math.round((b.count / histogram.max) * 56 + 4));
                    const isPeak = b.count === histogram.max && b.count > 0;
                    return (
                      <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                        <div
                          title={`${b.label}: ${b.count} logs${b.errorCount ? ` • ${b.errorCount} errors` : ''}${b.warnCount ? ` • ${b.warnCount} warnings` : ''}`}
                          style={{
                            width: '100%',
                            height: h,
                            borderRadius: 3,
                            background: b.count === 0 ? 'rgba(255,255,255,0.08)' : isPeak ? 'linear-gradient(180deg, #60a5fa, #3b82f6)' : '#334155',
                            border: isPeak ? '1px solid rgba(96,165,250,0.6)' : '1px solid transparent',
                            transition: 'height 0.25s ease',
                          }}
                        />
                      </div>
                    );
                  })}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 10, color: 'var(--text-dim, #8c909f)', fontFamily: 'var(--font-mono, monospace)' }}>
                  {histogram.buckets.map((b, i) => (
                    <span key={i} style={{ flex: 1, textAlign: 'center', opacity: histogram.buckets.length > 14 ? (i % 3 === 0 ? 1 : 0) : i % 2 === 0 ? 1 : 0 }}>
                      {b.label}
                    </span>
                  ))}
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 4, fontSize: 10, color: 'var(--text-dim, #8c909f)' }}>
                  <span>0</span>
                  <span>{Math.round(histogram.max / 2)}</span>
                  <span>{histogram.max} logs</span>
                </div>
              </>
            )}
          </div>

          {/* Table panel */}
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 380,
              background: 'var(--bg-panel, #131b2e)',
              border: '1px solid var(--border-color, #424754)',
              borderRadius: 10,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '118px 84px 150px 1fr 148px 84px 18px',
                gap: 10,
                padding: '9px 10px 8px 12px',
                borderBottom: '1px solid var(--border-color, #424754)',
                background: 'rgba(255,255,255,0.02)',
                fontSize: 10,
                fontWeight: 800,
                letterSpacing: 0.5,
                color: 'var(--text-dim, #8c909f)',
                textTransform: 'uppercase',
                position: 'sticky',
                top: 0,
                zIndex: 1,
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                THỜI GIAN <Filter size={10} style={{ opacity: 0.6 }} />
              </span>
              <span>MỨC LOG</span>
              <span>NGUỒN / DỊCH VỤ</span>
              <span>THÔNG ĐIỆP</span>
              <span>TRACE ID</span>
              <span style={{ textAlign: 'center' }}>TRẠNG THÁI</span>
              <span />
            </div>

            <div ref={tableWrapRef} style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', minHeight: 0 }}>
              {isLoading && <div style={{ padding: 16, color: 'var(--text-muted, #c2c6d6)', fontSize: 12.5 }}>Đang tải logs từ API…</div>}
              {error && <div style={{ padding: 12, color: '#f87171', fontSize: 12 }}>Không thể tải logs: {(error as Error).message}</div>}
              {!isLoading && !error && pageSlice.length === 0 && (
                <div style={{ padding: '22px 16px', color: 'var(--text-muted, #9ca3af)', fontSize: 12.5, textAlign: 'center' }}>
                  Không có log nào khớp bộ lọc.
                  <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-dim, #8c909f)' }}>
                    {merged.length === 0 ? 'Hoạt động runtime sẽ xuất hiện tại đây khi có sự kiện mới qua WebSocket / API.' : 'Thử nới lỏng filter hoặc chọn khoảng thời gian rộng hơn.'}
                  </div>
                </div>
              )}
              {pageSlice.map((r, idx) => {
                const lvl = (r.level ?? 'INFO').toUpperCase();
                const st = LEVEL_STYLE[lvl] ?? LEVEL_STYLE.INFO;
                // Position prefix keeps duplicate log rows (same timestamp,
                // trace id and message) from colliding on one React key.
                const key = `${idx}|${r.timestamp}|${r.trace_id ?? ''}|${r.message}`;
                const isSelected = selected && `${selected.timestamp}|${selected.trace_id ?? ''}|${selected.message}` === key;
                const statusColor =
                  lvl === 'ERROR' || lvl === 'CRITICAL' ? '#ef4444' : lvl === 'WARNING' || lvl === 'WARN' ? '#f59e0b' : lvl === 'DEBUG' ? '#8c909f' : '#10b981';
                return (
                  <div
                    key={key}
                    onClick={() => {
                      setSelectedKey(key);
                      setShowDetail(true);
                    }}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '118px 84px 150px 1fr 148px 84px 18px',
                      gap: 10,
                      alignItems: 'center',
                      padding: '7px 10px 7px 12px',
                      borderBottom: '1px solid rgba(255,255,255,0.04)',
                      background: isSelected ? 'rgba(77,142,255,0.08)' : 'transparent',
                      cursor: 'pointer',
                      transition: 'background 0.12s ease',
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.03)';
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                    }}
                  >
                    <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 11, color: 'var(--text-dim, #8c909f)', whiteSpace: 'nowrap' }}>
                      {fmtTime(r.timestamp)}
                    </span>
                    <span>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          minWidth: 54,
                          padding: '2px 6px',
                          borderRadius: 5,
                          fontSize: 10,
                          fontWeight: 800,
                          letterSpacing: 0.4,
                          background: st.bg,
                          color: st.fg,
                          border: `1px solid ${st.border}`,
                        }}
                      >
                        {LEVEL_LABEL[lvl] ?? lvl}
                      </span>
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted, #c2c6d6)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.source}>
                      {r.source || '—'}
                    </span>
                    <span
                      style={{
                        fontSize: 11.5,
                        color: lvl === 'ERROR' || lvl === 'CRITICAL' ? '#e6e8f2' : '#dbe4ff',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={r.message}
                    >
                      {r.message || '—'}
                      {r.metadata && (r.metadata as { step_id?: string })?.step_id ? (
                        <span
                          style={{
                            marginLeft: 6,
                            fontFamily: 'var(--font-mono, monospace)',
                            fontSize: 10,
                            color: '#8b9cf0',
                            background: 'rgba(139,156,240,0.12)',
                            border: '1px solid rgba(139,156,240,0.22)',
                            borderRadius: 4,
                            padding: '1px 4px',
                          }}
                        >
                          {(r.metadata as { step_id?: string }).step_id}
                        </span>
                      ) : null}
                    </span>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: 10.5,
                        color: 'var(--text-dim, #8c909f)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={r.trace_id ?? ''}
                    >
                      {r.trace_id ?? '—'}
                    </span>
                    <span style={{ display: 'flex', justifyContent: 'center' }}>
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor, boxShadow: `0 0 8px ${statusColor}`, display: 'inline-block' }} />
                    </span>
                    <span style={{ display: 'flex', justifyContent: 'center', color: 'var(--text-dim, #8c909f)' }}>
                      <ChevronRight size={12} style={{ opacity: isSelected ? 1 : 0.35 }} />
                    </span>
                  </div>
                );
              })}
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 10,
                padding: '8px 10px',
                borderTop: '1px solid var(--border-color, #424754)',
                background: 'rgba(0,0,0,0.12)',
                fontSize: 11,
                color: 'var(--text-muted, #c2c6d6)',
                flexWrap: 'wrap',
              }}
            >
              <span style={{ fontSize: 11, color: 'var(--text-dim, #8c909f)' }}>
                Hiển thị {filtered.length === 0 ? 0 : (page - 1) * pageSize + 1} – {Math.min(page * pageSize, filtered.length)} của {fmtNumber(filtered.length)} logs
                {live.length > 0 && !isPaused ? <span style={{ color: '#4edea3', marginLeft: 6 }}>• {live.length} live</span> : null}
                {isWsLive ? null : <span style={{ color: '#f87171', marginLeft: 6 }}>• WS offline</span>}
              </span>

              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} style={pagerBtnStyle(page <= 1)}>
                  <ChevronLeft size={13} />
                </button>
                {Array.from({ length: Math.min(totalPages, 6) }, (_, i) => {
                  let n: number | string;
                  if (totalPages <= 6) n = i + 1;
                  else if (page <= 3) n = i < 5 ? i + 1 : '…';
                  else if (page >= totalPages - 2) n = i === 0 ? 1 : i === 1 ? '…' : totalPages - (5 - i);
                  else n = i === 0 ? 1 : i === 1 ? '…' : i === 5 ? totalPages : page + (i - 3);
                  if (n === '…')
                    return (
                      <span key={`e-${i}`} style={{ padding: '0 4px', color: 'var(--text-dim, #8c909f)' }}>
                        …
                      </span>
                    );
                  const nn = n as number;
                  const active = nn === page;
                  return (
                    <button
                      key={nn}
                      onClick={() => setPage(nn)}
                      style={{
                        minWidth: 26,
                        height: 26,
                        borderRadius: 6,
                        border: `1px solid ${active ? 'rgba(77,142,255,0.45)' : 'var(--border-color, #424754)'}`,
                        background: active ? 'rgba(77,142,255,0.16)' : 'transparent',
                        color: active ? '#60a5fa' : 'var(--text-muted, #c2c6d6)',
                        fontSize: 11,
                        fontWeight: active ? 700 : 500,
                        cursor: 'pointer',
                      }}
                    >
                      {nn}
                    </button>
                  );
                })}
                {totalPages > 6 && (
                  <button
                    onClick={() => setPage(totalPages)}
                    style={{
                      minWidth: 26,
                      height: 26,
                      borderRadius: 6,
                      border: `1px solid ${page === totalPages ? 'rgba(77,142,255,0.45)' : 'var(--border-color, #424754)'}`,
                      background: page === totalPages ? 'rgba(77,142,255,0.16)' : 'transparent',
                      color: page === totalPages ? '#60a5fa' : 'var(--text-muted, #c2c6d6)',
                      fontSize: 11,
                      cursor: 'pointer',
                    }}
                  >
                    {totalPages}
                  </button>
                )}
                <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} style={pagerBtnStyle(page >= totalPages)}>
                  <ChevronRight size={13} />
                </button>

                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setPage(1);
                  }}
                  style={{
                    marginLeft: 8,
                    padding: '4px 6px',
                    borderRadius: 6,
                    border: '1px solid var(--border-color, #424754)',
                    background: '#0b1220',
                    color: 'var(--text-muted, #c2c6d6)',
                    fontSize: 11,
                  }}
                >
                  {pageSizeOptions.map((n) => (
                    <option key={n} value={n}>
                      {n} / trang
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '7px 12px', borderTop: '1px solid var(--border-color, #424754)', background: 'rgba(255,255,255,0.015)', fontSize: 11, fontWeight: 700 }}>
              {(['Stream', 'Traces', 'Metrics', 'Services', 'Sources'] as const).map((t) => {
                const active = activeTab === t;
                return (
                  <button
                    key={t}
                    onClick={() => setActiveTab(t)}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      borderBottom: `2px solid ${active ? '#4d8eff' : 'transparent'}`,
                      color: active ? '#60a5fa' : 'var(--text-dim, #8c909f)',
                      padding: '4px 2px 6px 2px',
                      cursor: 'pointer',
                      fontSize: 11,
                      fontWeight: 700,
                      letterSpacing: 0.2,
                    }}
                  >
                    {t}
                  </button>
                );
              })}
              <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-dim, #8c909f)', fontWeight: 500 }}>
                {activeTab === 'Stream' ? `${filtered.length} events trong view` : `${activeTab} – sắp ra mắt`}
              </span>
            </div>
          </div>
        </div>

        {/* Detail inspector – only real fields */}
        {showDetail && selected ? (
          <div
            style={{
              width: 360,
              minWidth: 320,
              maxWidth: 420,
              display: 'flex',
              flexDirection: 'column',
              background: 'var(--bg-panel, #131b2e)',
              border: '1px solid var(--border-color, #424754)',
              borderRadius: 10,
              overflow: 'hidden',
              alignSelf: 'stretch',
              maxHeight: 'calc(100vh - 96px)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '9px 10px',
                borderBottom: '1px solid var(--border-color, #424754)',
                background: 'rgba(255,255,255,0.02)',
              }}
            >
              <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: 0.6, color: 'var(--text-muted, #c2c6d6)', textTransform: 'uppercase' }}>CHI TIẾT SỰ KIỆN</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <button
                  onClick={() => handleCopy(JSON.stringify(selected, null, 2))}
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: 6,
                    border: '1px solid var(--border-color, #424754)',
                    background: 'transparent',
                    color: 'var(--text-dim, #8c909f)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                  }}
                  title="Copy JSON"
                >
                  <Copy size={11} />
                </button>
                <button
                  onClick={() => setShowDetail(false)}
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: 6,
                    border: '1px solid var(--border-color, #424754)',
                    background: 'transparent',
                    color: 'var(--text-dim, #8c909f)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                  }}
                >
                  <X size={11} />
                </button>
              </span>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: '10px 11px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 11, color: 'var(--text-dim, #8c909f)' }} title={selected.timestamp}>
                    {selected.timestamp ? new Date(selected.timestamp).toLocaleString('vi-VN') : '—'}
                  </span>
                  <span
                    style={{
                      padding: '1px 6px',
                      borderRadius: 5,
                      fontSize: 9,
                      fontWeight: 800,
                      letterSpacing: 0.4,
                      background: LEVEL_STYLE[(selected.level ?? 'INFO').toUpperCase()]?.bg ?? 'rgba(239,68,68,0.16)',
                      color: LEVEL_STYLE[(selected.level ?? 'INFO').toUpperCase()]?.fg ?? '#f87171',
                      border: `1px solid ${LEVEL_STYLE[(selected.level ?? 'INFO').toUpperCase()]?.border ?? 'rgba(239,68,68,0.32)'}`,
                      textTransform: 'uppercase',
                    }}
                  >
                    {(LEVEL_LABEL[(selected.level ?? '').toUpperCase()] ?? selected.level) || 'INFO'}
                  </span>
                </div>
                <div style={{ marginTop: 4, fontFamily: 'var(--font-mono, monospace)', fontSize: 10.5, color: 'var(--text-dim, #8c909f)' }}>{relativeTime(selected.timestamp)}</div>
                <div style={{ marginTop: 8, fontSize: 12.5, fontWeight: 700, color: '#e6e8f2', lineHeight: 1.35 }}>{selected.message || '—'}</div>
              </div>

              <DetailIdRow label="Trace ID" value={selected.trace_id ?? '—'} onCopy={handleCopy} />
              <DetailIdRow label="Correlation ID" value={selected.correlation_id ?? '—'} onCopy={handleCopy} />

              {/* Grid – only real values, "—" when absent */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: 8,
                  padding: '8px',
                  borderRadius: 8,
                  background: 'rgba(0,0,0,0.18)',
                  border: '1px solid rgba(255,255,255,0.06)',
                }}
              >
                <MiniField label="Nguồn" value={selected.source || '—'} />
                <MiniField
                  label="Agent / Run"
                  value={(selected.agent_instance_id as string) || selected.task_id || (selected.conversation_id as string) || '—'}
                  mono
                />
                <MiniField
                  label="Conversation"
                  value={(selected.conversation_id as string) || '—'}
                  mono
                />
                <MiniField
                  label="Task"
                  value={(selected.task_id as string) || '—'}
                  mono
                />
                <MiniField label="Session" value={(selected.metadata as { session_id?: string })?.session_id ?? '—'} mono />
                <MiniField label="Correlation" value={(selected.correlation_id as string) || '—'} mono />
              </div>

              {/* Tags – only if real tags exist */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: 0.5, color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', marginBottom: 6 }}>TAGS</div>
                {(() => {
                  const md = selected.metadata as Record<string, unknown> | undefined;
                  const rawTags = md?.tags as unknown;
                  let tags: string[] = [];
                  if (Array.isArray(rawTags)) tags = rawTags.filter((t): t is string => typeof t === 'string');
                  else if (typeof md?.tag === 'string') tags = [md.tag as string];
                  if (tags.length === 0) {
                    return <div style={{ fontSize: 11, color: 'var(--text-dim, #8c909f)', fontStyle: 'italic' }}>Không có tags trong metadata</div>;
                  }
                  const palette: Record<string, { bg: string; fg: string }> = {
                    render: { bg: 'rgba(77,142,255,0.14)', fg: '#60a5fa' },
                    gpu: { bg: 'rgba(16,185,129,0.14)', fg: '#4edea3' },
                    frame: { bg: 'rgba(245,158,11,0.14)', fg: '#fbbf24' },
                    oom: { bg: 'rgba(239,68,68,0.14)', fg: '#f87171' },
                    critical: { bg: 'rgba(239,68,68,0.22)', fg: '#ffb4ab' },
                  };
                  return (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {tags.slice(0, 12).map((t) => (
                        <span
                          key={t}
                          style={{
                            padding: '2px 7px',
                            borderRadius: 5,
                            fontSize: 10,
                            fontWeight: 700,
                            background: palette[t]?.bg ?? 'rgba(255,255,255,0.06)',
                            color: palette[t]?.fg ?? 'var(--text-muted, #c2c6d6)',
                            border: '1px solid rgba(255,255,255,0.06)',
                          }}
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  );
                })()}
              </div>

              {/* Metadata – real JSON only */}
              <CollapsibleSection
                title="METADATA"
                expanded={metaExpanded}
                onToggle={() => setMetaExpanded((v) => !v)}
                badge={`${Object.keys((selected.metadata as object) ?? {}).length} keys`}
              >
                {(() => {
                  const md = selected.metadata as Record<string, unknown> | undefined;
                  const hasMd = md && Object.keys(md).length > 0;
                  if (!hasMd) return <div style={{ fontSize: 11, color: 'var(--text-dim, #8c909f)', padding: '8px 0', fontStyle: 'italic' }}>Không có metadata</div>;
                  return (
                    <pre
                      style={{
                        margin: 0,
                        padding: '8px 9px',
                        borderRadius: 8,
                        background: '#070b18',
                        border: '1px solid rgba(255,255,255,0.06)',
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: 10.5,
                        lineHeight: 1.45,
                        color: '#cbd5e1',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                        maxHeight: 180,
                        overflowY: 'auto',
                      }}
                    >
                      {JSON.stringify(md, null, 2)}
                    </pre>
                  );
                })()}
              </CollapsibleSection>

              {/* Payload preview – from real metadata.payload if present, else message */}
              <CollapsibleSection title="PAYLOAD (PREVIEW)" expanded={payloadExpanded} onToggle={() => setPayloadExpanded((v) => !v)} mono>
                {(() => {
                  const md = selected.metadata as Record<string, unknown> | undefined;
                  const payload = md?.payload as unknown;
                  const preview: Record<string, unknown> = {};
                  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
                    Object.assign(preview, payload as Record<string, unknown>);
                  } else if (payload != null) {
                    (preview as Record<string, unknown>).payload = payload as unknown as string;
                  }
                  // always include message as fallback so panel is not empty
                  if (Object.keys(preview).length === 0) {
                    preview.message = selected.message;
                    if (selected.trace_id) preview.trace_id = selected.trace_id;
                    if (selected.correlation_id) preview.correlation_id = selected.correlation_id;
                  }
                  return (
                    <pre
                      style={{
                        margin: 0,
                        padding: '8px 9px',
                        borderRadius: 8,
                        background: '#070b18',
                        border: '1px solid rgba(255,255,255,0.06)',
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: 10.5,
                        lineHeight: 1.45,
                        color: '#cbd5e1',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                        maxHeight: 140,
                        overflowY: 'auto',
                      }}
                    >
                      {JSON.stringify(preview, null, 2)}
                    </pre>
                  );
                })()}
              </CollapsibleSection>

              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button
                  onClick={() => handleCopy(JSON.stringify(selected, null, 2))}
                  style={{
                    flex: 1,
                    minWidth: 120,
                    padding: '7px 8px',
                    borderRadius: 7,
                    border: '1px solid var(--border-color, #424754)',
                    background: 'rgba(255,255,255,0.04)',
                    color: 'var(--text-muted, #c2c6d6)',
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                  }}
                >
                  <Maximize2 size={12} /> Xem đầy đủ JSON
                </button>
              </div>

              <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: 0.5, color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', marginTop: 2 }}>Liên kết nhanh</div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button onClick={() => handleCopy(selected.trace_id ?? '')} style={quickLinkBtnStyle()} title="Copy Trace ID">
                  <Eye size={11} /> Xem Trace
                </button>
                <button onClick={() => handleCopy((selected.correlation_id as string) ?? '')} style={quickLinkBtnStyle()}>
                  <Copy size={11} /> Xem Run
                </button>
                <button
                  onClick={() => {
                    window.location.hash = '#/monitoring';
                  }}
                  style={quickLinkBtnStyle()}
                >
                  <Activity size={11} /> Mở trong Monitor
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {!showDetail && selected && (
        <button
          onClick={() => setShowDetail(true)}
          style={{
            position: 'fixed',
            right: 16,
            bottom: 16,
            padding: '9px 12px',
            borderRadius: 999,
            border: '1px solid rgba(77,142,255,0.32)',
            background: 'rgba(77,142,255,0.16)',
            color: '#60a5fa',
            fontSize: 11,
            fontWeight: 700,
            cursor: 'pointer',
            boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Eye size={13} /> Chi tiết ({LEVEL_LABEL[(selected.level ?? '').toUpperCase()] ?? selected.level})
        </button>
      )}
    </div>
  );
};

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

function MetricCard({
  title,
  value,
  deltaText,
  deltaColor,
  deltaUp,
  sub,
  live,
  sparkValues,
  sparkColor,
}: {
  title: string;
  value: string;
  deltaText?: string;
  deltaColor?: string;
  deltaUp?: boolean;
  sub?: string;
  live?: boolean;
  sparkValues: number[];
  sparkColor: string;
}) {
  const hasSpark = sparkValues.length > 1 && sparkValues.some((v) => v !== 0);
  const empty = sparkValues.length === 0 || sparkValues.every((v) => v === 0);
  return (
    <div
      style={{
        background: 'var(--bg-panel, #131b2e)',
        border: '1px solid var(--border-color, #424754)',
        borderRadius: 10,
        padding: '12px 12px 10px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        minHeight: 92,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: 0.6, color: 'var(--text-muted, #c2c6d6)', textTransform: 'uppercase' }}>{title}</div>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: -0.5, lineHeight: 1, color: 'var(--text-main, #dae2fd)' }}>{value}</div>
          {deltaText ? (
            <div style={{ marginTop: 5, display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 11, fontWeight: 700, color: deltaColor }}>
              {deltaUp !== undefined && !deltaText.includes('chưa đủ') && !deltaText.startsWith('0%') ? <span style={{ fontSize: 10 }}>{deltaUp ? '▲' : '▼'}</span> : null} {deltaText}
            </div>
          ) : null}
          {sub ? (
            <div style={{ marginTop: 4, display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-dim, #8c909f)' }}>
              {live !== undefined ? (
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: live ? '#4edea3' : '#8c909f', boxShadow: live ? '0 0 6px #4edea3' : 'none', display: 'inline-block' }} />
              ) : null}
              {sub}
            </div>
          ) : null}
        </div>
        {empty ? (
          <span style={{ fontSize: 10, color: 'var(--text-dim, #8c909f)', fontStyle: 'italic', flexShrink: 0 }}>—</span>
        ) : (
          <svg width={68} height={24} viewBox="0 0 68 24" style={{ flexShrink: 0, overflow: 'visible', opacity: hasSpark ? 1 : 0.35 }}>
            <path d={sparkPath(sparkValues, 68, 24)} fill="none" stroke={sparkColor} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" opacity={0.95} />
          </svg>
        )}
      </div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  labels,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  labels?: Record<string, string>;
  placeholder?: string;
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase' }}>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: '6px 22px 6px 8px',
          borderRadius: 7,
          border: '1px solid var(--border-color, #2a3347)',
          background: '#0b1220',
          color: 'var(--text-muted, #c2c6d6)',
          fontSize: 11.5,
          minWidth: 110,
          outline: 'none',
        }}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o === '' ? placeholder ?? 'Tất cả' : labels?.[o] ?? o}
          </option>
        ))}
      </select>
    </label>
  );
}

function DetailIdRow({ label, value, onCopy }: { label: string; value: string; onCopy: (v: string) => void }) {
  const isEmpty = !value || value === '—';
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', minWidth: 90 }}>{label}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, justifyContent: 'flex-end' }}>
        <span
          style={{
            fontFamily: 'var(--font-mono, monospace)',
            fontSize: 10.5,
            color: isEmpty ? 'var(--text-dim, #8c909f)' : 'var(--text-muted, #c2c6d6)',
            fontStyle: isEmpty ? 'italic' : 'normal',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            maxWidth: 190,
          }}
          title={value}
        >
          {value}
        </span>
        <button
          onClick={() => onCopy(value)}
          disabled={isEmpty}
          style={{
            width: 20,
            height: 20,
            borderRadius: 5,
            border: '1px solid rgba(255,255,255,0.08)',
            background: 'rgba(255,255,255,0.04)',
            color: isEmpty ? 'var(--text-dim, #8c909f)' : 'var(--text-dim, #8c909f)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: isEmpty ? 'not-allowed' : 'pointer',
            opacity: isEmpty ? 0.45 : 1,
            flexShrink: 0,
          }}
          title={isEmpty ? 'Không có ID để copy' : `Copy ${label}`}
        >
          <Copy size={10} />
        </button>
      </span>
    </div>
  );
}

function MiniField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  const isEmpty = !value || value === '—';
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase' }}>{label}</div>
      <div
        style={{
          marginTop: 2,
          fontSize: 11,
          color: isEmpty ? 'var(--text-dim, #8c909f)' : 'var(--text-muted, #c2c6d6)',
          fontStyle: isEmpty ? 'italic' : 'normal',
          fontFamily: mono ? 'var(--font-mono, monospace)' : undefined,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={value}
      >
        {value}
      </div>
    </div>
  );
}

function CollapsibleSection({
  title,
  expanded,
  onToggle,
  children,
  badge,
  mono,
}: {
  title: string;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  badge?: string;
  mono?: boolean;
}) {
  return (
    <div>
      <button
        onClick={onToggle}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          padding: 0,
          marginBottom: expanded ? 6 : 0,
        }}
      >
        <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: 0.5, color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', fontFamily: mono ? 'var(--font-mono, monospace)' : undefined }}>{title}</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--text-dim, #8c909f)' }}>
          {badge ? <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 4, padding: '1px 5px' }}>{badge}</span> : null}
          <span style={{ fontSize: 11, lineHeight: 1, transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.15s' }}>⌃</span>
        </span>
      </button>
      {expanded && children}
    </div>
  );
}

function toolbarBtnStyle(active?: boolean): React.CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    padding: '6px 9px',
    borderRadius: 7,
    border: `1px solid ${active ? 'rgba(77,142,255,0.32)' : 'var(--border-color, #424754)'}`,
    background: active ? 'rgba(77,142,255,0.10)' : 'rgba(255,255,255,0.03)',
    color: 'var(--text-muted, #c2c6d6)',
    fontSize: 11,
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    opacity: active === false ? 0.9 : 1,
  };
}

function pagerBtnStyle(disabled: boolean): React.CSSProperties {
  return {
    width: 26,
    height: 26,
    borderRadius: 6,
    border: '1px solid var(--border-color, #424754)',
    background: 'transparent',
    color: disabled ? 'var(--text-dim, #8c909f)' : 'var(--text-muted, #c2c6d6)',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  };
}

function quickLinkBtnStyle(): React.CSSProperties {
  return {
    flex: 1,
    padding: '6px 8px',
    borderRadius: 7,
    border: '1px solid var(--border-color, #424754)',
    background: 'rgba(255,255,255,0.03)',
    color: 'var(--text-muted, #c2c6d6)',
    fontSize: 11,
    fontWeight: 600,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    whiteSpace: 'nowrap',
  };
}
