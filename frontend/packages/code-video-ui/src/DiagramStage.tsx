import React from 'react';
import { DiagramState } from './types';

export interface DiagramStageProps {
  state: DiagramState;
}

export const DiagramStage: React.FC<DiagramStageProps> = ({ state }) => {
  const width = 1600;
  const height = 900;
  const nodeCount = Math.max(1, state.nodes.length);
  const spacing = Math.floor(width / (nodeCount + 1));
  const nodeWidth = 240;
  const nodeHeight = 120;
  const yCenter = height / 2;

  const nodeCoords: Record<string, { cx: number; cy: number }> = {};
  state.nodes.forEach((n, idx) => {
    nodeCoords[n.id] = { cx: spacing * (idx + 1), cy: yCenter };
  });

  const categoryColors: Record<string, string> = {
    user: '#7ee787',
    domain: '#58a6ff',
    infrastructure: '#d29922',
    output: '#a371f7',
    concept: '#f0883e',
  };

  return (
    <div className="layout-diagram">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height="100%"
        className="diagram-svg"
      >
        <rect width="100%" height="100%" fill="#0d1117" />
        <text
          x={width / 2}
          y={80}
          textAnchor="middle"
          fill="#58a6ff"
          fontFamily="system-ui, sans-serif"
          fontSize={32}
          fontWeight="bold"
        >
          {state.title}
        </text>
        <text
          x={width / 2}
          y={120}
          textAnchor="middle"
          fill="#8b949e"
          fontFamily="system-ui, sans-serif"
          fontSize={20}
        >
          {state.subtitle}
        </text>

        {/* Edges */}
        {state.edges.map((edge, idx) => {
          const s = nodeCoords[edge.source_id];
          const t = nodeCoords[edge.target_id];
          if (!s || !t) return null;
          const x1 = s.cx + nodeWidth / 2;
          const x2 = t.cx - nodeWidth / 2;
          const strokeColor = edge.style === 'animated' ? '#58a6ff' : '#30363d';
          const strokeDash = edge.style === 'dashed' ? '6,6' : undefined;

          return (
            <g key={idx}>
              <line
                x1={x1}
                y1={s.cy}
                x2={x2}
                y2={t.cy}
                stroke={strokeColor}
                strokeWidth={3}
                strokeDasharray={strokeDash}
              />
              {edge.label && (
                <text
                  x={(x1 + x2) / 2}
                  y={s.cy - 15}
                  textAnchor="middle"
                  fill="#8b949e"
                  fontSize={14}
                >
                  {edge.label}
                </text>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {state.nodes.map((node) => {
          const pos = nodeCoords[node.id];
          if (!pos) return null;
          const rx = pos.cx - nodeWidth / 2;
          const ry = pos.cy - nodeHeight / 2;
          const isHl =
            node.highlighted || state.highlighted_nodes.includes(node.id);
          const badgeColor = categoryColors[node.category] || '#58a6ff';

          return (
            <g key={node.id} className="diagram-node">
              <rect
                x={rx}
                y={ry}
                width={nodeWidth}
                height={nodeHeight}
                rx={12}
                fill={isHl ? '#1f242c' : '#161b22'}
                stroke={isHl ? '#388bfd' : '#30363d'}
                strokeWidth={2}
                filter={isHl ? 'drop-shadow(0 0 12px rgba(56,139,253,0.5))' : undefined}
              />
              <rect
                x={rx + 12}
                y={ry + 12}
                width={80}
                height={20}
                rx={4}
                fill={`${badgeColor}22`}
              />
              <text
                x={rx + 52}
                y={ry + 26}
                textAnchor="middle"
                fill={badgeColor}
                fontFamily="system-ui, sans-serif"
                fontSize={11}
                fontWeight={600}
              >
                {node.category.toUpperCase()}
              </text>
              <text
                x={pos.cx}
                y={pos.cy + 10}
                textAnchor="middle"
                fill="#c9d1d9"
                fontFamily="system-ui, sans-serif"
                fontSize={20}
                fontWeight="bold"
              >
                {node.label}
              </text>
              {node.subtext && (
                <text
                  x={pos.cx}
                  y={pos.cy + 34}
                  textAnchor="middle"
                  fill="#8b949e"
                  fontFamily="system-ui, sans-serif"
                  fontSize={13}
                >
                  {node.subtext}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};
