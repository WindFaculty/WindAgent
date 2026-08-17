import React, { useState } from 'react';
import type { RoutingRuleResource } from '@windagent/api-contracts';
import { useRoutingRules, useRoutingGraph, useRoutingMetrics, useUpdateRoutingRule } from '../hooks/useRouting';
import { RoutingMetrics } from '../components/RoutingMetrics';
import { RoutingRules } from '../components/RoutingRules';
import { RoutingRuleEditor } from '../components/RoutingRuleEditor';
import { RouteGraph } from '../components/RouteGraph';
import { TrafficDistribution } from '../components/TrafficDistribution';
import { RouteSimulator } from '../components/RouteSimulator';

export const RoutingPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'rules' | 'graph' | 'simulator'>('rules');
  const [editingRule, setEditingRule] = useState<RoutingRuleResource | null>(null);
  const [isCreatingNew, setIsCreatingNew] = useState(false);

  const { data: rules = [] } = useRoutingRules();
  const { data: graph, isLoading: isLoadingGraph } = useRoutingGraph();
  const { data: metrics, isLoading: isLoadingMetrics } = useRoutingMetrics();
  const updateMutation = useUpdateRoutingRule();

  const handleToggleEnabled = async (rule: RoutingRuleResource) => {
    await updateMutation.mutateAsync({
      ruleId: rule.id,
      updates: { enabled: !rule.enabled, expected_version: rule.version },
    });
  };

  return (
    <div
      style={{
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        maxWidth: '1600px',
        margin: '0 auto',
        fontFamily: 'var(--font-sans, sans-serif)',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
            Model Routing & Policy Hub
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
            Configure priority-based routing rules, visualize network graph distribution, and test explainable decisions.
          </p>
        </div>
      </div>

      {/* Metrics Banner */}
      <RoutingMetrics metrics={metrics} isLoading={isLoadingMetrics} />

      {/* Navigation Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          borderBottom: '1px solid var(--border-color, #1f2937)',
          paddingBottom: '8px',
        }}
      >
        <button
          type="button"
          onClick={() => setActiveTab('rules')}
          style={{
            padding: '8px 16px',
            borderRadius: '6px',
            backgroundColor: activeTab === 'rules' ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
            color: activeTab === 'rules' ? '#60a5fa' : 'var(--text-muted, #9ca3af)',
            border: activeTab === 'rules' ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid transparent',
            fontWeight: 600,
            fontSize: '0.85rem',
            cursor: 'pointer',
          }}
        >
          Routing Rules
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('graph')}
          style={{
            padding: '8px 16px',
            borderRadius: '6px',
            backgroundColor: activeTab === 'graph' ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
            color: activeTab === 'graph' ? '#60a5fa' : 'var(--text-muted, #9ca3af)',
            border: activeTab === 'graph' ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid transparent',
            fontWeight: 600,
            fontSize: '0.85rem',
            cursor: 'pointer',
          }}
        >
          Graph & Distribution
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('simulator')}
          style={{
            padding: '8px 16px',
            borderRadius: '6px',
            backgroundColor: activeTab === 'simulator' ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
            color: activeTab === 'simulator' ? '#60a5fa' : 'var(--text-muted, #9ca3af)',
            border: activeTab === 'simulator' ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid transparent',
            fontWeight: 600,
            fontSize: '0.85rem',
            cursor: 'pointer',
          }}
        >
          Route Simulator
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'rules' && (
        <RoutingRules
          rules={rules}
          onCreateRule={() => {
            setEditingRule(null);
            setIsCreatingNew(true);
          }}
          onEditRule={(rule) => {
            setEditingRule(rule);
            setIsCreatingNew(false);
          }}
          onToggleEnabled={handleToggleEnabled}
        />
      )}

      {activeTab === 'graph' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <RouteGraph graph={graph} isLoading={isLoadingGraph} />
          {metrics && <TrafficDistribution distribution={metrics.traffic_distribution} />}
        </div>
      )}

      {activeTab === 'simulator' && <RouteSimulator />}

      {/* Editor Modal */}
      {(isCreatingNew || editingRule) && (
        <RoutingRuleEditor
          rule={editingRule}
          onSaved={() => {
            setIsCreatingNew(false);
            setEditingRule(null);
          }}
          onCancelled={() => {
            setIsCreatingNew(false);
            setEditingRule(null);
          }}
        />
      )}
    </div>
  );
};
