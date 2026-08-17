/**
 * StudioActivityChart (Phase 6).
 * Interactive SVG activity curve visualizing real studio production events.
 */

import React, { useState } from 'react';
import { BarChart3, Lightbulb, FileText, Film, Clapperboard } from 'lucide-react';
import type { DashboardSummary } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';
import type { ActivityTimeframe } from '../model/types';

export interface StudioActivityChartProps {
  summary?: DashboardSummary;
}

export const StudioActivityChart: React.FC<StudioActivityChartProps> = ({ summary }) => {
  const [timeframe, setTimeframe] = useState<ActivityTimeframe>('7d');

  const timeframePoints = summary?.activity_by_timeframe?.[timeframe] ?? [];

  // Totals for metrics counter row
  const totalIdeas = timeframePoints.reduce((acc, p) => acc + p.ideas_count, 0);
  const totalOutlines = timeframePoints.reduce((acc, p) => acc + p.outlines_count, 0);
  const totalScripts = timeframePoints.reduce((acc, p) => acc + p.scripts_count, 0);
  const totalRenders = timeframePoints.reduce((acc, p) => acc + p.renders_count, 0);

  // Generate SVG path from points
  const generateSvgPath = () => {
    if (!timeframePoints || timeframePoints.length === 0) return { areaPath: '', linePath: '', coords: [] };
    const width = 1000;
    const height = 180;
    const maxVal = Math.max(...timeframePoints.map((p) => p.total_activity), 10);
    const step = width / Math.max(1, timeframePoints.length - 1);

    const coords = timeframePoints.map((val, idx) => {
      const x = idx * step;
      const y = height - (val.total_activity / maxVal) * (height - 40) - 20;
      return { x, y, label: val.label, value: val.total_activity };
    });

    let linePath = `M ${coords[0].x} ${coords[0].y}`;
    for (let i = 0; i < coords.length - 1; i++) {
      const p0 = coords[i];
      const p1 = coords[i + 1];
      const cx = (p0.x + p1.x) / 2;
      linePath += ` C ${cx} ${p0.y}, ${cx} ${p1.y}, ${p1.x} ${p1.y}`;
    }

    const areaPath = `${linePath} L ${coords[coords.length - 1].x} ${height} L ${coords[0].x} ${height} Z`;
    return { areaPath, linePath, coords };
  };

  const { areaPath, linePath, coords } = generateSvgPath();

  return (
    <Card
      elevation="raised"
      style={{
        padding: '24px',
        background: 'linear-gradient(135deg, rgba(23, 31, 51, 0.9), rgba(15, 23, 42, 0.95))',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '12px',
        marginBottom: '24px',
      }}
      data-testid="studio-activity-chart"
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(77, 142, 255, 0.15)', color: '#4d8eff' }}>
            <BarChart3 size={20} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#f8fafc' }}>
              Hoạt Động Sáng Tác & Kịch Bản Phim
            </h3>
            <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#94a3b8' }}>
              Tốc độ sinh Idea, Outline, Screenplay và Render kịch bản theo thời gian
            </p>
          </div>
        </div>

        {/* Timeframe Filter Buttons */}
        <div style={{ display: 'flex', background: 'rgba(255,255,255,0.05)', padding: '3px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)' }}>
          {(['24h', '7d', '30d', '90d'] as ActivityTimeframe[]).map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              style={{
                padding: '4px 12px',
                border: 'none',
                background: timeframe === tf ? '#4d8eff' : 'transparent',
                color: timeframe === tf ? '#ffffff' : '#94a3b8',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* SVG Chart Area */}
      <div style={{ width: '100%', height: '180px', position: 'relative', marginBottom: '20px' }}>
        <svg viewBox="0 0 1000 180" preserveAspectRatio="none" style={{ width: '100%', height: '100%', overflow: 'visible' }}>
          <defs>
            <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#4d8eff" stopOpacity="0.35" />
              <stop offset="70%" stopColor="#4d8eff" stopOpacity="0.08" />
              <stop offset="100%" stopColor="#4d8eff" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line x1="0" y1="40" x2="1000" y2="40" stroke="rgba(255,255,255,0.06)" strokeDasharray="4 4" />
          <line x1="0" y1="90" x2="1000" y2="90" stroke="rgba(255,255,255,0.06)" strokeDasharray="4 4" />
          <line x1="0" y1="140" x2="1000" y2="140" stroke="rgba(255,255,255,0.06)" strokeDasharray="4 4" />

          {/* Filled Area */}
          {areaPath && <path d={areaPath} fill="url(#chartGradient)" />}

          {/* Line Stroke */}
          {linePath && <path d={linePath} fill="none" stroke="#4d8eff" strokeWidth="3" strokeLinecap="round" />}

          {/* Dots */}
          {coords.map((c, i) => (
            <g key={i}>
              <circle cx={c.x} cy={c.y} r="4" fill="#4d8eff" stroke="#0f172a" strokeWidth="2" />
            </g>
          ))}
        </svg>

        {/* Labels below chart */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px' }}>
          {coords.map((c, i) => (
            <span key={i} style={{ fontSize: '11px', color: '#64748b' }}>
              {c.label}
            </span>
          ))}
        </div>
      </div>

      {/* Metric Counters Breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', paddingTop: '16px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
            <Lightbulb size={16} />
          </div>
          <div>
            <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>{totalIdeas}</div>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>Ideas Sinh Ra</div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(77, 142, 255, 0.15)', color: '#4d8eff' }}>
            <FileText size={16} />
          </div>
          <div>
            <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>{totalOutlines}</div>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>Outlines Cốt Truyện</div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(78, 222, 163, 0.15)', color: '#4edea3' }}>
            <Film size={16} />
          </div>
          <div>
            <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>{totalScripts}</div>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>Kịch Bản Chi Tiết</div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(192, 193, 255, 0.15)', color: '#c0c1ff' }}>
            <Clapperboard size={16} />
          </div>
          <div>
            <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>{totalRenders}</div>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>Renders Hoàn Tất</div>
          </div>
        </div>
      </div>
    </Card>
  );
};
