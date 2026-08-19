import React, { useState, useMemo } from 'react';
import type { RoutingRuleResource } from '@windagent/api-contracts';
import {
  Search,
  Plus,
  Zap,
  Shield,
  ShieldAlert,
  Cpu,
  ArrowRight,
  Sparkles,
  Edit3,
  SlidersHorizontal,
  Play,
  RotateCcw,
  Lock,
  Layers,
} from 'lucide-react';

interface RoutingRulesProps {
  rules: RoutingRuleResource[];
  onSelectRule?: (rule: RoutingRuleResource) => void;
  onEditRule?: (rule: RoutingRuleResource) => void;
  onToggleEnabled?: (rule: RoutingRuleResource) => void;
  onCreateRule?: () => void;
  onSimulateRule?: (rule: RoutingRuleResource) => void;
}

export const RoutingRules: React.FC<RoutingRulesProps> = ({
  rules,
  onEditRule,
  onToggleEnabled,
  onCreateRule,
  onSimulateRule,
}) => {
  const [search, setSearch] = useState('');
  const [selectedPriority, setSelectedPriority] = useState<string>('all');
  const [selectedRole, setSelectedRole] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'enabled' | 'disabled'>('all');
  const [sortBy, setSortBy] = useState<'priority' | 'latency' | 'success' | 'name'>('priority');

  // Extract distinct roles
  const allRoles = useMemo(() => {
    const set = new Set<string>();
    rules.forEach((r) => r.agent_types?.forEach((at) => set.add(at)));
    return Array.from(set).sort();
  }, [rules]);

  // Filter and sort rules
  const filteredRules = useMemo(() => {
    return rules
      .filter((rule) => {
        // Search filter
        if (search.trim()) {
          const q = search.toLowerCase();
          const matchName = rule.name.toLowerCase().includes(q);
          const matchId = rule.id.toLowerCase().includes(q);
          const matchDesc = rule.description?.toLowerCase().includes(q);
          const matchModel = rule.canonical_model_id.toLowerCase().includes(q);
          const matchFallback = rule.fallback_model_id?.toLowerCase().includes(q);
          const matchRole = rule.agent_types?.some((at) => at.toLowerCase().includes(q));
          const matchCap = rule.required_capabilities?.some((rc) => rc.toLowerCase().includes(q));
          if (!matchName && !matchId && !matchDesc && !matchModel && !matchFallback && !matchRole && !matchCap) {
            return false;
          }
        }

        // Priority filter
        if (selectedPriority !== 'all') {
          if (selectedPriority === 'p0' && rule.priority > 0) return false;
          if (selectedPriority === 'p10' && (rule.priority <= 0 || rule.priority > 10)) return false;
          if (selectedPriority === 'p50' && (rule.priority <= 10 || rule.priority > 50)) return false;
          if (selectedPriority === 'low' && rule.priority <= 50) return false;
        }

        // Role filter
        if (selectedRole !== 'all' && !rule.agent_types?.includes(selectedRole)) {
          return false;
        }

        // Status filter
        if (statusFilter === 'enabled' && !rule.enabled) return false;
        if (statusFilter === 'disabled' && rule.enabled) return false;

        return true;
      })
      .sort((a, b) => {
        if (sortBy === 'priority') return a.priority - b.priority;
        if (sortBy === 'latency') return a.avg_latency_ms - b.avg_latency_ms;
        if (sortBy === 'success') return b.success_rate - a.success_rate;
        if (sortBy === 'name') return a.name.localeCompare(b.name);
        return 0;
      });
  }, [rules, search, selectedPriority, selectedRole, statusFilter, sortBy]);

  const getPriorityTheme = (priority: number) => {
    if (priority <= 0) {
      return {
        label: 'Critical (P0)',
        color: '#f87171',
        bg: 'rgba(239, 68, 68, 0.15)',
        border: 'rgba(239, 68, 68, 0.4)',
        glow: 'rgba(239, 68, 68, 0.25)',
        icon: ShieldAlert,
      };
    }
    if (priority <= 10) {
      return {
        label: `High (P${priority})`,
        color: '#fbbf24',
        bg: 'rgba(245, 158, 11, 0.15)',
        border: 'rgba(245, 158, 11, 0.4)',
        glow: 'rgba(245, 158, 11, 0.2)',
        icon: Zap,
      };
    }
    if (priority <= 50) {
      return {
        label: `Normal (P${priority})`,
        color: '#60a5fa',
        bg: 'rgba(59, 130, 246, 0.15)',
        border: 'rgba(59, 130, 246, 0.4)',
        glow: 'rgba(59, 130, 246, 0.15)',
        icon: Cpu,
      };
    }
    return {
      label: `Low (P${priority})`,
      color: '#9ca3af',
      bg: 'rgba(156, 163, 175, 0.15)',
      border: 'rgba(156, 163, 175, 0.3)',
      glow: 'transparent',
      icon: Layers,
    };
  };

  const getProviderBadge = (modelId: string) => {
    if (modelId.startsWith('anthropic/')) {
      return { provider: 'Anthropic', color: '#fb923c', bg: 'rgba(251, 146, 60, 0.12)', border: 'rgba(251, 146, 60, 0.3)' };
    }
    if (modelId.startsWith('google/')) {
      return { provider: 'Google AI', color: '#60a5fa', bg: 'rgba(96, 165, 250, 0.12)', border: 'rgba(96, 165, 250, 0.3)' };
    }
    if (modelId.startsWith('openai/')) {
      return { provider: 'OpenAI', color: '#2dd4bf', bg: 'rgba(45, 212, 191, 0.12)', border: 'rgba(45, 212, 191, 0.3)' };
    }
    if (modelId.startsWith('deepseek/')) {
      return { provider: 'DeepSeek', color: '#c084fc', bg: 'rgba(192, 132, 252, 0.12)', border: 'rgba(192, 132, 252, 0.3)' };
    }
    if (modelId.startsWith('ollama/')) {
      return { provider: 'Ollama (Local)', color: '#4edea3', bg: 'rgba(78, 222, 163, 0.12)', border: 'rgba(78, 222, 163, 0.3)' };
    }
    return { provider: 'Hermes Mesh', color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.12)', border: 'rgba(148, 163, 184, 0.3)' };
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '18px',
      }}
    >
      {/* Search and Action Toolbar */}
      <div
        style={{
          padding: '16px 20px',
          borderRadius: '12px',
          backgroundColor: 'rgba(19, 27, 46, 0.75)',
          border: '1px solid rgba(66, 71, 84, 0.4)',
          backdropFilter: 'blur(16px)',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '14px',
        }}
      >
        {/* Left: Search & Filter inputs */}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px', flex: '1 1 auto' }}>
          {/* Search Box */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: 'rgba(11, 19, 38, 0.8)',
              border: '1px solid rgba(66, 71, 84, 0.5)',
              borderRadius: '8px',
              padding: '6px 12px',
              minWidth: '260px',
              flex: '1 1 260px',
            }}
          >
            <Search size={16} color="var(--text-muted, #c2c6d6)" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search policies, roles, models, tags..."
              style={{
                background: 'transparent',
                border: 'none',
                outline: 'none',
                color: 'var(--text-main, #dae2fd)',
                fontSize: '0.85rem',
                width: '100%',
                fontFamily: 'var(--font-sans)',
              }}
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-dim, #8c909f)',
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                  padding: 0,
                }}
              >
                ✕
              </button>
            )}
          </div>

          {/* Priority Filter */}
          <select
            value={selectedPriority}
            onChange={(e) => setSelectedPriority(e.target.value)}
            style={{
              padding: '7px 12px',
              backgroundColor: 'rgba(11, 19, 38, 0.8)',
              border: '1px solid rgba(66, 71, 84, 0.5)',
              borderRadius: '8px',
              color: 'var(--text-main, #dae2fd)',
              fontSize: '0.82rem',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Priorities</option>
            <option value="p0">Critical (P0)</option>
            <option value="p10">High (P1 - P10)</option>
            <option value="p50">Normal (P11 - P50)</option>
            <option value="low">Low (P50+)</option>
          </select>

          {/* Role Filter */}
          <select
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value)}
            style={{
              padding: '7px 12px',
              backgroundColor: 'rgba(11, 19, 38, 0.8)',
              border: '1px solid rgba(66, 71, 84, 0.5)',
              borderRadius: '8px',
              color: 'var(--text-main, #dae2fd)',
              fontSize: '0.82rem',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Agent Roles</option>
            {allRoles.map((r) => (
              <option key={r} value={r}>
                Role: {r}
              </option>
            ))}
          </select>

          {/* Sort Filter */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            style={{
              padding: '7px 12px',
              backgroundColor: 'rgba(11, 19, 38, 0.8)',
              border: '1px solid rgba(66, 71, 84, 0.5)',
              borderRadius: '8px',
              color: 'var(--text-main, #dae2fd)',
              fontSize: '0.82rem',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="priority">Sort: Priority (Asc)</option>
            <option value="latency">Sort: Lowest Latency</option>
            <option value="success">Sort: Highest Success</option>
            <option value="name">Sort: Rule Name</option>
          </select>
        </div>

        {/* Right: Create Button & Counter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-dim, #8c909f)', fontWeight: 500 }}>
            Showing <strong style={{ color: 'var(--text-main, #dae2fd)' }}>{filteredRules.length}</strong> of {rules.length}
          </span>

          {onCreateRule && (
            <button
              type="button"
              onClick={onCreateRule}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 16px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #4d8eff 0%, #2563eb 100%)',
                color: '#ffffff',
                border: '1px solid rgba(173, 198, 255, 0.4)',
                boxShadow: '0 4px 14px rgba(77, 142, 255, 0.35)',
                cursor: 'pointer',
                fontSize: '0.82rem',
                fontWeight: 700,
                letterSpacing: '0.01em',
                transition: 'all 0.15s ease',
              }}
            >
              <Plus size={16} />
              <span>Create Rule</span>
            </button>
          )}
        </div>
      </div>

      {/* Rules List */}
      {filteredRules.length === 0 ? (
        <div
          style={{
            padding: '48px 24px',
            textAlign: 'center',
            backgroundColor: 'rgba(19, 27, 46, 0.5)',
            borderRadius: '12px',
            border: '1px dashed rgba(66, 71, 84, 0.5)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <SlidersHorizontal size={36} color="var(--text-dim, #8c909f)" />
          <h4 style={{ margin: 0, color: 'var(--text-main, #dae2fd)', fontSize: '1rem', fontWeight: 600 }}>
            No routing rules match your filters
          </h4>
          <p style={{ margin: 0, color: 'var(--text-dim, #8c909f)', fontSize: '0.82rem' }}>
            Try resetting your search query or selecting &ldquo;All Priorities&rdquo;.
          </p>
          <button
            type="button"
            onClick={() => {
              setSearch('');
              setSelectedPriority('all');
              setSelectedRole('all');
              setStatusFilter('all');
            }}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              backgroundColor: 'rgba(77, 142, 255, 0.15)',
              border: '1px solid rgba(77, 142, 255, 0.3)',
              color: '#adc6ff',
              fontSize: '0.8rem',
              cursor: 'pointer',
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <RotateCcw size={14} /> Reset Filters
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {filteredRules.map((rule) => {
            const pTheme = getPriorityTheme(rule.priority);
            const PriorityIcon = pTheme.icon;
            const primaryProvider = getProviderBadge(rule.canonical_model_id);
            const fallbackProvider = rule.fallback_model_id ? getProviderBadge(rule.fallback_model_id) : null;

            return (
              <div
                key={rule.id}
                style={{
                  padding: '18px 20px',
                  borderRadius: '12px',
                  backgroundColor: 'rgba(19, 27, 46, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.4)',
                  borderLeft: `4px solid ${pTheme.color}`,
                  backdropFilter: 'blur(16px)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                  position: 'relative',
                  opacity: rule.enabled ? 1 : 0.65,
                  boxShadow: rule.enabled
                    ? `0 4px 20px -2px rgba(0, 0, 0, 0.4), 0 0 16px -4px ${pTheme.glow}`
                    : 'none',
                  transition: 'all 0.2s ease',
                }}
              >
                {/* Top Section: Badges, Title, ID, and Enabled Switch */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px' }}>
                    {/* Priority Badge */}
                    <span
                      style={{
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        padding: '3px 8px',
                        borderRadius: '6px',
                        backgroundColor: pTheme.bg,
                        color: pTheme.color,
                        border: `1px solid ${pTheme.border}`,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        textTransform: 'uppercase',
                        letterSpacing: '0.03em',
                      }}
                    >
                      <PriorityIcon size={12} />
                      {pTheme.label}
                    </span>

                    {/* Rule Name */}
                    <h3
                      style={{
                        margin: 0,
                        fontSize: '1.05rem',
                        fontWeight: 700,
                        color: 'var(--text-main, #dae2fd)',
                        letterSpacing: '-0.01em',
                      }}
                    >
                      {rule.name}
                    </h3>

                    {/* Rule ID and Version */}
                    <code
                      style={{
                        fontSize: '0.72rem',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        backgroundColor: 'rgba(11, 19, 38, 0.6)',
                        border: '1px solid rgba(66, 71, 84, 0.4)',
                        color: 'var(--text-dim, #8c909f)',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {rule.id} • v{rule.version}
                    </code>

                    {rule.requires_local && (
                      <span
                        style={{
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: 'rgba(78, 222, 163, 0.15)',
                          color: '#4edea3',
                          border: '1px solid rgba(78, 222, 163, 0.3)',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '3px',
                        }}
                      >
                        <Lock size={10} /> Offline Privacy-Locked
                      </span>
                    )}
                  </div>

                  {/* Right Header: Toggle switch and Action Buttons */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
                    {/* Toggle Switch */}
                    {onToggleEnabled && (
                      <button
                        type="button"
                        onClick={() => onToggleEnabled(rule)}
                        title={rule.enabled ? 'Click to disable policy' : 'Click to enable policy'}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '4px 10px',
                          borderRadius: '20px',
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          backgroundColor: rule.enabled ? 'rgba(78, 222, 163, 0.15)' : 'rgba(140, 144, 159, 0.15)',
                          color: rule.enabled ? '#4edea3' : 'var(--text-dim, #8c909f)',
                          border: rule.enabled ? '1px solid rgba(78, 222, 163, 0.4)' : '1px solid rgba(66, 71, 84, 0.5)',
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        <span
                          style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            backgroundColor: rule.enabled ? '#4edea3' : '#8c909f',
                            boxShadow: rule.enabled ? '0 0 8px #4edea3' : 'none',
                          }}
                        />
                        {rule.enabled ? 'Enabled' : 'Disabled'}
                      </button>
                    )}

                    {/* Quick Test / Simulate */}
                    {onSimulateRule && (
                      <button
                        type="button"
                        onClick={() => onSimulateRule(rule)}
                        title="Simulate routing with this rule's predicates"
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '4px 10px',
                          borderRadius: '6px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          backgroundColor: 'rgba(77, 142, 255, 0.12)',
                          color: '#adc6ff',
                          border: '1px solid rgba(77, 142, 255, 0.3)',
                          cursor: 'pointer',
                        }}
                      >
                        <Play size={12} /> Test
                      </button>
                    )}

                    {/* Edit Button */}
                    {onEditRule && (
                      <button
                        type="button"
                        onClick={() => onEditRule(rule)}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '4px 10px',
                          borderRadius: '6px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          backgroundColor: 'rgba(34, 42, 61, 0.8)',
                          color: 'var(--text-main, #dae2fd)',
                          border: '1px solid rgba(66, 71, 84, 0.5)',
                          cursor: 'pointer',
                        }}
                      >
                        <Edit3 size={12} /> Edit
                      </button>
                    )}
                  </div>
                </div>

                {/* Description */}
                {rule.description && (
                  <p
                    style={{
                      margin: 0,
                      fontSize: '0.84rem',
                      color: 'var(--text-muted, #c2c6d6)',
                      lineHeight: 1.4,
                    }}
                  >
                    {rule.description}
                  </p>
                )}

                {/* Visual Pipeline Flow Box */}
                <div
                  style={{
                    padding: '12px 14px',
                    borderRadius: '8px',
                    backgroundColor: 'rgba(11, 19, 38, 0.65)',
                    border: '1px solid rgba(66, 71, 84, 0.3)',
                    display: 'flex',
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '12px',
                  }}
                >
                  {/* Left Pipeline Flow: Target Roles ➔ Primary Model ➔ Fallback */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px' }}>
                    {/* Role Triggers */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)', fontWeight: 600, textTransform: 'uppercase' }}>
                        Triggers:
                      </span>
                      {rule.agent_types.map((at) => (
                        <span
                          key={at}
                          style={{
                            fontSize: '0.72rem',
                            fontWeight: 600,
                            padding: '2px 7px',
                            borderRadius: '4px',
                            backgroundColor: 'rgba(192, 132, 252, 0.12)',
                            color: '#d8b4fe',
                            border: '1px solid rgba(192, 132, 252, 0.25)',
                          }}
                        >
                          Role: {at}
                        </span>
                      ))}
                    </div>

                    <ArrowRight size={14} color="var(--text-dim, #8c909f)" />

                    {/* Primary Model Target */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)', fontWeight: 600, textTransform: 'uppercase' }}>
                        Primary:
                      </span>
                      <div
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          backgroundColor: primaryProvider.bg,
                          border: `1px solid ${primaryProvider.border}`,
                        }}
                      >
                        <Zap size={12} color={primaryProvider.color} />
                        <code style={{ fontSize: '0.78rem', color: primaryProvider.color, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                          {rule.canonical_model_id}
                        </code>
                        <span
                          style={{
                            fontSize: '0.68rem',
                            color: 'var(--text-dim, #8c909f)',
                            paddingLeft: '4px',
                            borderLeft: '1px solid rgba(255,255,255,0.1)',
                          }}
                        >
                          {primaryProvider.provider}
                        </span>
                      </div>
                    </div>

                    {/* Fallback Model (if configured) */}
                    {rule.fallback_model_id && fallbackProvider && (
                      <>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-dim, #8c909f)' }}>↳ failover</span>
                        <div
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            padding: '3px 8px',
                            borderRadius: '6px',
                            backgroundColor: fallbackProvider.bg,
                            border: `1px solid ${fallbackProvider.border}`,
                          }}
                        >
                          <Shield size={12} color={fallbackProvider.color} />
                          <code style={{ fontSize: '0.78rem', color: fallbackProvider.color, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                            {rule.fallback_model_id}
                          </code>
                        </div>
                      </>
                    )}
                  </div>

                  {/* Right: Live Health / Performance Stats */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexShrink: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem' }}>
                      <span style={{ color: 'var(--text-dim, #8c909f)' }}>Success:</span>
                      <strong style={{ color: '#4edea3', fontWeight: 700 }}>{rule.success_rate}%</strong>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem' }}>
                      <span style={{ color: 'var(--text-dim, #8c909f)' }}>Latency:</span>
                      <strong style={{ color: '#38bdf8', fontWeight: 700 }}>{rule.avg_latency_ms}ms</strong>
                    </div>
                  </div>
                </div>

                {/* Capability and Requirement Tags */}
                {rule.required_capabilities && rule.required_capabilities.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', fontWeight: 600 }}>
                      Requirements:
                    </span>
                    {rule.required_capabilities.map((rc) => (
                      <span
                        key={rc}
                        style={{
                          fontSize: '0.7rem',
                          padding: '1px 6px',
                          borderRadius: '4px',
                          backgroundColor: 'rgba(77, 142, 255, 0.1)',
                          color: '#adc6ff',
                          border: '1px solid rgba(77, 142, 255, 0.2)',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '3px',
                        }}
                      >
                        <Sparkles size={10} /> {rc}
                      </span>
                    ))}
                    {rule.requires_tools && (
                      <span
                        style={{
                          fontSize: '0.7rem',
                          padding: '1px 6px',
                          borderRadius: '4px',
                          backgroundColor: 'rgba(251, 191, 36, 0.1)',
                          color: '#fbbf24',
                          border: '1px solid rgba(251, 191, 36, 0.25)',
                        }}
                      >
                        ⚡ Tools Enabled
                      </span>
                    )}
                    {rule.requires_vision && (
                      <span
                        style={{
                          fontSize: '0.7rem',
                          padding: '1px 6px',
                          borderRadius: '4px',
                          backgroundColor: 'rgba(244, 114, 182, 0.1)',
                          color: '#f472b6',
                          border: '1px solid rgba(244, 114, 182, 0.25)',
                        }}
                      >
                        👁️ Multimodal
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
