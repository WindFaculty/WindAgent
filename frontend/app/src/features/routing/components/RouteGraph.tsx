import React, { useState } from 'react';
import type { RoutingGraphData } from '@windagent/api-contracts';
import {
  Network,
  Cpu,
  ArrowRight,
  Shield,
  Zap,
  Bot,
  Activity,
} from 'lucide-react';

interface RouteGraphProps {
  graph?: RoutingGraphData;
  isLoading?: boolean;
}

export const RouteGraph: React.FC<RouteGraphProps> = ({ graph, isLoading }) => {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  if (isLoading || !graph) {
    return (
      <div
        style={{
          padding: '60px 20px',
          textAlign: 'center',
          backgroundColor: 'rgba(19, 27, 46, 0.7)',
          borderRadius: '12px',
          border: '1px solid rgba(66, 71, 84, 0.4)',
          color: 'var(--text-muted, #c2c6d6)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
        }}
      >
        <Activity size={32} color="#4d8eff" className="animate-spin" />
        <span>Loading routing topology graph and network routing matrix...</span>
      </div>
    );
  }

  const roleNodes = graph.nodes.filter((n) => n.type === 'role');
  const ruleNodes = graph.nodes.filter((n) => n.type === 'rule');
  const modelNodes = graph.nodes.filter((n) => n.type === 'model' || n.type === 'provider');

  // Helper to determine if a node is linked to the currently selected node
  const isNodeConnected = (nodeId: string) => {
    if (!selectedNodeId) return false;
    if (nodeId === selectedNodeId) return true;

    // Check direct links
    const directLink = graph.links.some(
      (l) => (l.source === selectedNodeId && l.target === nodeId) || (l.source === nodeId && l.target === selectedNodeId)
    );
    if (directLink) return true;

    // Check 2-hop links (role -> rule -> model)
    const middleRules = graph.links
      .filter((l) => l.source === selectedNodeId || l.target === selectedNodeId)
      .map((l) => (l.source === selectedNodeId ? l.target : l.source));

    return graph.links.some(
      (l) => (middleRules.includes(l.source) && l.target === nodeId) || (middleRules.includes(l.target) && l.source === nodeId)
    );
  };

  const getProviderInfo = (label: string) => {
    if (label.toLowerCase().includes('claude') || label.toLowerCase().includes('anthropic')) {
      return { provider: 'Anthropic', color: '#fb923c', bg: 'rgba(251, 146, 60, 0.12)', border: 'rgba(251, 146, 60, 0.3)' };
    }
    if (label.toLowerCase().includes('gemini') || label.toLowerCase().includes('google')) {
      return { provider: 'Google AI', color: '#60a5fa', bg: 'rgba(96, 165, 250, 0.12)', border: 'rgba(96, 165, 250, 0.3)' };
    }
    if (label.toLowerCase().includes('gpt') || label.toLowerCase().includes('openai')) {
      return { provider: 'OpenAI', color: '#2dd4bf', bg: 'rgba(45, 212, 191, 0.12)', border: 'rgba(45, 212, 191, 0.3)' };
    }
    if (label.toLowerCase().includes('deepseek')) {
      return { provider: 'DeepSeek', color: '#c084fc', bg: 'rgba(192, 132, 252, 0.12)', border: 'rgba(192, 132, 252, 0.3)' };
    }
    if (label.toLowerCase().includes('qwen') || label.toLowerCase().includes('ollama') || label.toLowerCase().includes('local')) {
      return { provider: 'Ollama (Local)', color: '#4edea3', bg: 'rgba(78, 222, 163, 0.12)', border: 'rgba(78, 222, 163, 0.3)' };
    }
    return { provider: 'Cloud Gateway', color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.12)', border: 'rgba(148, 163, 184, 0.3)' };
  };

  return (
    <div
      style={{
        padding: '24px',
        borderRadius: '14px',
        backgroundColor: 'rgba(19, 27, 46, 0.75)',
        border: '1px solid rgba(66, 71, 84, 0.4)',
        backdropFilter: 'blur(16px)',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        boxShadow: '0 8px 32px -4px rgba(0, 0, 0, 0.4)',
      }}
    >
      {/* Header & Interactive hint */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Network size={20} color="#4d8eff" />
            <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main, #dae2fd)' }}>
              Routing Topology & Gateway Matrix
            </h3>
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.84rem', color: 'var(--text-muted, #c2c6d6)' }}>
            Live dependency graph mapping Agent Request Roles ➔ Policy Decision Matrix ➔ Canonical Target Endpoints.
          </p>
        </div>

        {/* Action / reset filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {selectedNodeId ? (
            <button
              type="button"
              onClick={() => setSelectedNodeId(null)}
              style={{
                padding: '5px 12px',
                borderRadius: '6px',
                backgroundColor: 'rgba(77, 142, 255, 0.15)',
                border: '1px solid rgba(77, 142, 255, 0.3)',
                color: '#adc6ff',
                fontSize: '0.78rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              ✕ Clear Path Highlight
            </button>
          ) : (
            <span style={{ fontSize: '0.78rem', color: 'var(--text-dim, #8c909f)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              💡 Click any node to trace routing path
            </span>
          )}
        </div>
      </div>

      {/* 3-Column Visual Flow Matrix */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '20px',
          padding: '20px',
          backgroundColor: 'rgba(11, 19, 38, 0.7)',
          borderRadius: '12px',
          border: '1px solid rgba(66, 71, 84, 0.3)',
        }}
      >
        {/* Column 1: Agent Roles */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '6px', borderBottom: '1px solid rgba(192, 132, 252, 0.2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Bot size={16} color="#c084fc" />
              <h4 style={{ margin: 0, fontSize: '0.84rem', color: '#d8b4fe', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em' }}>
                1. Request Roles ({roleNodes.length})
              </h4>
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)' }}>Input</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {roleNodes.map((n) => {
              const isSelected = selectedNodeId === n.id;
              const isConnected = isNodeConnected(n.id);
              const isDimmed = selectedNodeId && !isSelected && !isConnected;

              return (
                <div
                  key={n.id}
                  onClick={() => setSelectedNodeId(isSelected ? null : n.id)}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '8px',
                    backgroundColor: isSelected
                      ? 'rgba(192, 132, 252, 0.25)'
                      : isConnected
                      ? 'rgba(192, 132, 252, 0.15)'
                      : 'rgba(19, 27, 46, 0.8)',
                    border: isSelected
                      ? '1px solid #c084fc'
                      : isConnected
                      ? '1px solid rgba(192, 132, 252, 0.5)'
                      : '1px solid rgba(66, 71, 84, 0.4)',
                    boxShadow: isSelected ? '0 0 16px rgba(192, 132, 252, 0.3)' : 'none',
                    color: isDimmed ? 'var(--text-dim, #8c909f)' : 'var(--text-main, #dae2fd)',
                    opacity: isDimmed ? 0.4 : 1,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div
                      style={{
                        width: '24px',
                        height: '24px',
                        borderRadius: '6px',
                        backgroundColor: 'rgba(192, 132, 252, 0.15)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#c084fc',
                        fontSize: '0.75rem',
                      }}
                    >
                      🤖
                    </div>
                    <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>{n.label}</span>
                  </div>
                  <ArrowRight size={14} color={isSelected || isConnected ? '#c084fc' : 'var(--text-dim, #8c909f)'} />
                </div>
              );
            })}
          </div>
        </div>

        {/* Column 2: Evaluation Rules */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '6px', borderBottom: '1px solid rgba(77, 142, 255, 0.2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Shield size={16} color="#60a5fa" />
              <h4 style={{ margin: 0, fontSize: '0.84rem', color: '#93c5fd', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em' }}>
                2. Policy Engine ({ruleNodes.length})
              </h4>
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)' }}>Evaluation</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {ruleNodes.map((n) => {
              const isSelected = selectedNodeId === n.id;
              const isConnected = isNodeConnected(n.id);
              const isDimmed = selectedNodeId && !isSelected && !isConnected;

              return (
                <div
                  key={n.id}
                  onClick={() => setSelectedNodeId(isSelected ? null : n.id)}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '8px',
                    backgroundColor: isSelected
                      ? 'rgba(77, 142, 255, 0.25)'
                      : isConnected
                      ? 'rgba(77, 142, 255, 0.15)'
                      : 'rgba(19, 27, 46, 0.8)',
                    border: isSelected
                      ? '1px solid #4d8eff'
                      : isConnected
                      ? '1px solid rgba(77, 142, 255, 0.5)'
                      : '1px solid rgba(66, 71, 84, 0.4)',
                    boxShadow: isSelected ? '0 0 16px rgba(77, 142, 255, 0.3)' : 'none',
                    color: isDimmed ? 'var(--text-dim, #8c909f)' : 'var(--text-main, #dae2fd)',
                    opacity: isDimmed ? 0.4 : 1,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div
                      style={{
                        width: '24px',
                        height: '24px',
                        borderRadius: '6px',
                        backgroundColor: 'rgba(77, 142, 255, 0.15)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#60a5fa',
                      }}
                    >
                      <Zap size={13} />
                    </div>
                    <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{n.label}</span>
                  </div>
                  <ArrowRight size={14} color={isSelected || isConnected ? '#60a5fa' : 'var(--text-dim, #8c909f)'} />
                </div>
              );
            })}
          </div>
        </div>

        {/* Column 3: Target Models */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '6px', borderBottom: '1px solid rgba(78, 222, 163, 0.2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Cpu size={16} color="#4edea3" />
              <h4 style={{ margin: 0, fontSize: '0.84rem', color: '#86efac', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em' }}>
                3. Canonical Models ({modelNodes.length})
              </h4>
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)' }}>Execution</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {modelNodes.map((n) => {
              const isSelected = selectedNodeId === n.id;
              const isConnected = isNodeConnected(n.id);
              const isDimmed = selectedNodeId && !isSelected && !isConnected;
              const pInfo = getProviderInfo(n.label);

              return (
                <div
                  key={n.id}
                  onClick={() => setSelectedNodeId(isSelected ? null : n.id)}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '8px',
                    backgroundColor: isSelected
                      ? 'rgba(78, 222, 163, 0.22)'
                      : isConnected
                      ? 'rgba(78, 222, 163, 0.12)'
                      : 'rgba(19, 27, 46, 0.8)',
                    border: isSelected
                      ? '1px solid #4edea3'
                      : isConnected
                      ? '1px solid rgba(78, 222, 163, 0.5)'
                      : '1px solid rgba(66, 71, 84, 0.4)',
                    boxShadow: isSelected ? '0 0 16px rgba(78, 222, 163, 0.3)' : 'none',
                    color: isDimmed ? 'var(--text-dim, #8c909f)' : 'var(--text-main, #dae2fd)',
                    opacity: isDimmed ? 0.4 : 1,
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.86rem', fontFamily: 'var(--font-mono)' }}>
                      {n.label}
                    </span>
                    <span
                      style={{
                        fontSize: '0.68rem',
                        fontWeight: 700,
                        padding: '1px 6px',
                        borderRadius: '4px',
                        backgroundColor: pInfo.bg,
                        color: pInfo.color,
                        border: `1px solid ${pInfo.border}`,
                      }}
                    >
                      {pInfo.provider}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
