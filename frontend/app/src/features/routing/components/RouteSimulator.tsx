import React, { useState } from 'react';
import type { RouteDecisionResource } from '@windagent/api-contracts';
import { useSimulateRoute } from '../hooks/useRouting';
import { RouteDecisionInspector } from './RouteDecisionInspector';

export const RouteSimulator: React.FC = () => {
  const simulateMutation = useSimulateRoute();

  const [role, setRole] = useState('Coordinator');
  const [prompt, setPrompt] = useState('Draft an episodic story beat outline with dialogue cues.');
  const [requiresVision, setRequiresVision] = useState(false);
  const [requiresTools, setRequiresTools] = useState(true);
  const [requiresLocal, setRequiresLocal] = useState(false);
  const [userPreferenceModel, setUserPreferenceModel] = useState('');
  const [decision, setDecision] = useState<RouteDecisionResource | null>(null);

  const handleSimulate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await simulateMutation.mutateAsync({
        role,
        prompt,
        requires_vision: requiresVision,
        requires_tools: requiresTools,
        requires_local: requiresLocal,
        user_preference_model: userPreferenceModel || undefined,
      });
      setDecision(res);
    } catch {
      // handled by mutation error
    }
  };

  return (
    <div
      style={{
        padding: '20px',
        borderRadius: '10px',
        backgroundColor: 'var(--bg-panel, #111827)',
        border: '1px solid var(--border-color, #1f2937)',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
      }}
    >
      <div>
        <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
          Routing Decision Simulator & Inspector
        </h3>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)' }}>
          Simulate runtime route resolution with request context, constraints, and audit the resulting RouteDecision.
        </span>
      </div>

      <form onSubmit={handleSimulate} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary, #d1d5db)' }}>
              Agent Role
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              style={{
                padding: '8px 12px',
                backgroundColor: 'var(--bg-subpanel, #1f2937)',
                border: '1px solid var(--border-color, #374151)',
                borderRadius: '6px',
                color: 'var(--text-primary, #f9fafb)',
                fontSize: '0.85rem',
              }}
            >
              <option value="Coordinator">Coordinator</option>
              <option value="Planner">Planner</option>
              <option value="Coder">Coder</option>
              <option value="VisualInspector">VisualInspector</option>
              <option value="Director">Director</option>
              <option value="Worker">Worker</option>
            </select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary, #d1d5db)' }}>
              User Model Override (Optional)
            </label>
            <input
              type="text"
              value={userPreferenceModel}
              onChange={(e) => setUserPreferenceModel(e.target.value)}
              placeholder="e.g. google/gemini-1.5-flash"
              style={{
                padding: '8px 12px',
                backgroundColor: 'var(--bg-subpanel, #1f2937)',
                border: '1px solid var(--border-color, #374151)',
                borderRadius: '6px',
                color: 'var(--text-primary, #f9fafb)',
                fontSize: '0.85rem',
              }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary, #d1d5db)' }}>
            Task Prompt / Intent
          </label>
          <textarea
            rows={2}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            style={{
              padding: '8px 12px',
              backgroundColor: 'var(--bg-subpanel, #1f2937)',
              border: '1px solid var(--border-color, #374151)',
              borderRadius: '6px',
              color: 'var(--text-primary, #f9fafb)',
              fontSize: '0.85rem',
              resize: 'vertical',
            }}
          />
        </div>

        {/* Constraint Checkboxes */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.82rem', color: 'var(--text-primary, #f9fafb)' }}>
            <input type="checkbox" checked={requiresTools} onChange={(e) => setRequiresTools(e.target.checked)} />
            Requires Tool Use
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.82rem', color: 'var(--text-primary, #f9fafb)' }}>
            <input type="checkbox" checked={requiresVision} onChange={(e) => setRequiresVision(e.target.checked)} />
            Requires Multimodal Vision
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.82rem', color: '#4ade80' }}>
            <input type="checkbox" checked={requiresLocal} onChange={(e) => setRequiresLocal(e.target.checked)} />
            Requires Offline / Local
          </label>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            type="submit"
            disabled={simulateMutation.isPending}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              backgroundColor: 'var(--color-primary, #2563eb)',
              color: '#ffffff',
              border: 'none',
              cursor: simulateMutation.isPending ? 'not-allowed' : 'pointer',
              fontSize: '0.85rem',
              fontWeight: 600,
              opacity: simulateMutation.isPending ? 0.7 : 1,
            }}
          >
            {simulateMutation.isPending ? 'Resolving Route...' : 'Simulate Route Decision'}
          </button>
        </div>
      </form>

      {/* Decision Output */}
      {decision && <RouteDecisionInspector decision={decision} />}
    </div>
  );
};
