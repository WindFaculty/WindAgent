import React, { useState } from 'react';
import type { RouteDecisionResource } from '@windagent/api-contracts';
import { useSimulateRoute } from '../hooks/useRouting';
import { RouteDecisionInspector } from './RouteDecisionInspector';
import {
  Play,
  Sparkles,
  Bot,
  Terminal,
  Zap,
  Lock,
  Eye,
  Sliders,
  RotateCcw,
  Activity,
} from 'lucide-react';

export const RouteSimulator: React.FC = () => {
  const simulateMutation = useSimulateRoute();

  const [role, setRole] = useState('Coordinator');
  const [prompt, setPrompt] = useState('Draft an episodic story beat outline with dialogue cues.');
  const [requiresVision, setRequiresVision] = useState(false);
  const [requiresTools, setRequiresTools] = useState(true);
  const [requiresLocal, setRequiresLocal] = useState(false);
  const [userPreferenceModel, setUserPreferenceModel] = useState('');
  const [decision, setDecision] = useState<RouteDecisionResource | null>(null);

  const presets = [
    {
      name: '💻 Offline Code Gen',
      role: 'Coder',
      prompt: 'Generate optimized TypeScript AST parsers and run local linters.',
      tools: true,
      vision: false,
      local: true,
      color: '#4edea3',
    },
    {
      name: '🎨 Multimodal Vision',
      role: 'VisualInspector',
      prompt: 'Inspect high-resolution keyframe rendering for cinematic lighting artifacts.',
      tools: false,
      vision: true,
      local: false,
      color: '#f472b6',
    },
    {
      name: '🧠 Master Planner',
      role: 'Planner',
      prompt: 'Draft 5-act episodic story beat outline with tension graph.',
      tools: true,
      vision: false,
      local: false,
      color: '#818cf8',
    },
    {
      name: '⚡ Fast Intent Router',
      role: 'Coordinator',
      prompt: 'Categorize incoming prompt intent and dispatch to worker agents.',
      tools: true,
      vision: false,
      local: false,
      color: '#fbbf24',
    },
  ];

  const applyPreset = (preset: typeof presets[0]) => {
    setRole(preset.role);
    setPrompt(preset.prompt);
    setRequiresTools(preset.tools);
    setRequiresVision(preset.vision);
    setRequiresLocal(preset.local);
  };

  const handleSimulate = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
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
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
      }}
    >
      {/* Simulation Form Card */}
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
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sliders size={20} color="#4d8eff" />
              <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main, #dae2fd)' }}>
                Routing Decision Simulator & Test Bench
              </h3>
            </div>
            <p style={{ margin: '4px 0 0 0', fontSize: '0.84rem', color: 'var(--text-muted, #c2c6d6)' }}>
              Simulate runtime request dispatching with intent prompts, constraint predicates, and audit explainable model locks.
            </p>
          </div>
        </div>

        {/* Quick Presets */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em' }}>
            ⚡ 1-Click Simulation Presets:
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {presets.map((p) => (
              <button
                key={p.name}
                type="button"
                onClick={() => applyPreset(p)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '8px',
                  backgroundColor: 'rgba(11, 19, 38, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  color: 'var(--text-main, #dae2fd)',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  transition: 'all 0.15s ease',
                }}
              >
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: p.color }} />
                {p.name}
              </button>
            ))}
          </div>
        </div>

        {/* Interactive Form */}
        <form onSubmit={handleSimulate} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '14px' }}>
            {/* Role Select */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted, #c2c6d6)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Bot size={14} color="#c084fc" /> Agent Role Context
              </label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                style={{
                  padding: '9px 12px',
                  backgroundColor: 'rgba(11, 19, 38, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  color: 'var(--text-main, #dae2fd)',
                  fontSize: '0.85rem',
                  outline: 'none',
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

            {/* Model Override */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted, #c2c6d6)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Sparkles size={14} color="#fbbf24" /> User Model Preference (Optional)
              </label>
              <input
                type="text"
                value={userPreferenceModel}
                onChange={(e) => setUserPreferenceModel(e.target.value)}
                placeholder="e.g. google/gemini-1.5-flash or leave empty for auto"
                style={{
                  padding: '9px 12px',
                  backgroundColor: 'rgba(11, 19, 38, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  color: 'var(--text-main, #dae2fd)',
                  fontSize: '0.85rem',
                  outline: 'none',
                  fontFamily: 'var(--font-mono)',
                }}
              />
            </div>
          </div>

          {/* Prompt / Intent Input */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted, #c2c6d6)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Terminal size={14} color="#38bdf8" /> Task Prompt / Intent Payload
            </label>
            <textarea
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              style={{
                padding: '10px 14px',
                backgroundColor: 'rgba(11, 19, 38, 0.8)',
                border: '1px solid rgba(66, 71, 84, 0.5)',
                borderRadius: '8px',
                color: 'var(--text-main, #dae2fd)',
                fontSize: '0.85rem',
                outline: 'none',
                resize: 'vertical',
                fontFamily: 'var(--font-sans)',
                lineHeight: 1.4,
              }}
            />
          </div>

          {/* Capability Toggles */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', padding: '12px 14px', backgroundColor: 'rgba(11, 19, 38, 0.6)', borderRadius: '8px', border: '1px solid rgba(66, 71, 84, 0.3)' }}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.82rem', color: 'var(--text-main, #dae2fd)' }}>
              <input
                type="checkbox"
                checked={requiresTools}
                onChange={(e) => setRequiresTools(e.target.checked)}
                style={{ accentColor: '#4d8eff', width: '16px', height: '16px' }}
              />
              <Zap size={14} color="#fbbf24" /> Requires Tool Use
            </label>

            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.82rem', color: 'var(--text-main, #dae2fd)' }}>
              <input
                type="checkbox"
                checked={requiresVision}
                onChange={(e) => setRequiresVision(e.target.checked)}
                style={{ accentColor: '#f472b6', width: '16px', height: '16px' }}
              />
              <Eye size={14} color="#f472b6" /> Requires Multimodal Vision
            </label>

            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.82rem', color: '#4edea3' }}>
              <input
                type="checkbox"
                checked={requiresLocal}
                onChange={(e) => setRequiresLocal(e.target.checked)}
                style={{ accentColor: '#4edea3', width: '16px', height: '16px' }}
              />
              <Lock size={14} color="#4edea3" /> Requires Offline / Privacy-Locked
            </label>
          </div>

          {/* Submit Action */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button
              type="button"
              onClick={() => {
                setRole('Coordinator');
                setPrompt('Draft an episodic story beat outline with dialogue cues.');
                setRequiresVision(false);
                setRequiresTools(true);
                setRequiresLocal(false);
                setUserPreferenceModel('');
                setDecision(null);
              }}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                backgroundColor: 'rgba(34, 42, 61, 0.8)',
                border: '1px solid rgba(66, 71, 84, 0.5)',
                color: 'var(--text-dim, #8c909f)',
                fontSize: '0.82rem',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <RotateCcw size={13} /> Reset
            </button>

            <button
              type="submit"
              disabled={simulateMutation.isPending}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                padding: '9px 22px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #4d8eff 0%, #2563eb 100%)',
                color: '#ffffff',
                border: '1px solid rgba(173, 198, 255, 0.4)',
                boxShadow: '0 4px 14px rgba(77, 142, 255, 0.35)',
                cursor: simulateMutation.isPending ? 'not-allowed' : 'pointer',
                fontSize: '0.85rem',
                fontWeight: 700,
                letterSpacing: '0.01em',
                opacity: simulateMutation.isPending ? 0.7 : 1,
              }}
            >
              {simulateMutation.isPending ? (
                <>
                  <Activity size={16} className="animate-spin" />
                  <span>Evaluating Policies...</span>
                </>
              ) : (
                <>
                  <Play size={16} />
                  <span>Simulate Route Decision</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Decision Output Inspector */}
      {decision && <RouteDecisionInspector decision={decision} />}
    </div>
  );
};
