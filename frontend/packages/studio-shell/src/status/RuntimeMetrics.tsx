import React from 'react';

export interface MetricState {
  cpu: number;
  ram: number;
  ramGb: number;
  ramTotalGb: number;
  gpu: number;
  gpuName: string;
  vram: number;
  vramGb: number;
  vramTotalGb: number;
  cpuHistory: number[];
  ramHistory: number[];
  gpuHistory: number[];
  vramHistory: number[];
}

export interface RuntimeMetricsProps {
  metrics: MetricState;
}

export const renderSparkline = (points: number[], maxVal: number): string => {
  if (!points || points.length === 0) return '0,14';
  const width = 50;
  const height = 14;
  const len = points.length;
  const xStep = width / Math.max(1, len - 1);
  const coords = points.map((p, i) => {
    const x = i * xStep;
    const y = height - (p / maxVal) * height;
    return `${x},${y}`;
  });
  return coords.join(' ');
};

export const RuntimeMetrics: React.FC<RuntimeMetricsProps> = ({ metrics }) => {
  return (
    <div className="header-metrics">
      <div className="metric-item">
        <span>CPU</span>
        <span className="metric-label">{metrics.cpu}%</span>
        <svg className="metric-sparkline">
          <polyline points={renderSparkline(metrics.cpuHistory, 100)} />
        </svg>
      </div>
      <div className="metric-item">
        <span>RAM</span>
        <span className="metric-label">
          {metrics.ram}% {metrics.ramGb} / {metrics.ramTotalGb || 16} GB
        </span>
        <svg className="metric-sparkline ram">
          <polyline points={renderSparkline(metrics.ramHistory, 100)} />
        </svg>
      </div>
      <div className="metric-item">
        <span>GPU</span>
        <span className="metric-label" title={metrics.gpuName}>
          {metrics.gpu}%
        </span>
        <svg className="metric-sparkline gpu">
          <polyline points={renderSparkline(metrics.gpuHistory, 100)} />
        </svg>
      </div>
      <div className="metric-item">
        <span>VRAM</span>
        <span className="metric-label">
          {metrics.vram}% {metrics.vramGb} / {metrics.vramTotalGb || 16} GB
        </span>
        <svg className="metric-sparkline vram">
          <polyline points={renderSparkline(metrics.vramHistory, 100)} />
        </svg>
      </div>
    </div>
  );
};

export default RuntimeMetrics;
