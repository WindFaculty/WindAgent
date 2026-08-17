import React, { useState, useMemo } from 'react';
import type { ModelDefinitionResource } from '@windagent/api-contracts';
import { useModels } from '../hooks/useModels';
import { ModelCapabilities } from '../components/ModelCapabilities';
import { ModelAvailability } from '../components/ModelAvailability';
import { ModelDetail } from '../components/ModelDetail';

export const ModelsPage: React.FC = () => {
  const [search, setSearch] = useState('');
  const [selectedProvider, setSelectedProvider] = useState<string>('all');
  const [selectedCapability, setSelectedCapability] = useState<string>('all');
  const [localOnly, setLocalOnly] = useState(false);
  const [activeModel, setActiveModel] = useState<ModelDefinitionResource | null>(null);

  const { data: models = [], isLoading, error } = useModels({
    provider: selectedProvider !== 'all' ? selectedProvider : undefined,
    capability: selectedCapability !== 'all' ? selectedCapability : undefined,
    is_local: localOnly ? true : undefined,
    search: search.trim() || undefined,
  });

  const providersList = useMemo(() => {
    const set = new Set<string>();
    models.forEach((m) => {
      set.add(m.vendor);
    });
    return Array.from(set);
  }, [models]);

  const stats = useMemo(() => {
    return {
      total: models.length,
      multimodal: models.filter((m) => m.capabilities.includes('vision') || m.capabilities.includes('audio')).length,
      local: models.filter((m) => m.is_local).length,
      reasoning: models.filter((m) => m.capabilities.includes('reasoning')).length,
    };
  }, [models]);

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
            AI Models & Intelligence Catalog
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
            Canonical model registry with capability metadata, context limits, and endpoint bindings.
          </p>
        </div>
      </div>

      {/* Stats Summary Bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '12px',
        }}
      >
        <div
          style={{
            padding: '14px 18px',
            borderRadius: '8px',
            backgroundColor: 'var(--bg-panel, #111827)',
            border: '1px solid var(--border-color, #1f2937)',
          }}
        >
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Total Models</span>
          <span style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-primary, #f9fafb)' }}>{stats.total}</span>
        </div>
        <div
          style={{
            padding: '14px 18px',
            borderRadius: '8px',
            backgroundColor: 'var(--bg-panel, #111827)',
            border: '1px solid var(--border-color, #1f2937)',
          }}
        >
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Multimodal / Vision</span>
          <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#f472b6' }}>{stats.multimodal}</span>
        </div>
        <div
          style={{
            padding: '14px 18px',
            borderRadius: '8px',
            backgroundColor: 'var(--bg-panel, #111827)',
            border: '1px solid var(--border-color, #1f2937)',
          }}
        >
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Reasoning Models</span>
          <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#f87171' }}>{stats.reasoning}</span>
        </div>
        <div
          style={{
            padding: '14px 18px',
            borderRadius: '8px',
            backgroundColor: 'var(--bg-panel, #111827)',
            border: '1px solid var(--border-color, #1f2937)',
          }}
        >
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Local / Offline</span>
          <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#4ade80' }}>{stats.local}</span>
        </div>
      </div>

      {/* Filter Controls */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '12px',
          padding: '14px',
          borderRadius: '8px',
          backgroundColor: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          alignItems: 'center',
        }}
      >
        <input
          type="text"
          placeholder="Search models by name, vendor, description..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            flex: '1 1 240px',
            padding: '8px 12px',
            backgroundColor: 'var(--bg-subpanel, #1f2937)',
            border: '1px solid var(--border-color, #374151)',
            borderRadius: '6px',
            color: 'var(--text-primary, #f9fafb)',
            fontSize: '0.85rem',
          }}
        />

        <select
          value={selectedProvider}
          onChange={(e) => setSelectedProvider(e.target.value)}
          style={{
            padding: '8px 12px',
            backgroundColor: 'var(--bg-subpanel, #1f2937)',
            border: '1px solid var(--border-color, #374151)',
            borderRadius: '6px',
            color: 'var(--text-primary, #f9fafb)',
            fontSize: '0.85rem',
          }}
        >
          <option value="all">All Vendors</option>
          {providersList.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        <select
          value={selectedCapability}
          onChange={(e) => setSelectedCapability(e.target.value)}
          style={{
            padding: '8px 12px',
            backgroundColor: 'var(--bg-subpanel, #1f2937)',
            border: '1px solid var(--border-color, #374151)',
            borderRadius: '6px',
            color: 'var(--text-primary, #f9fafb)',
            fontSize: '0.85rem',
          }}
        >
          <option value="all">All Capabilities</option>
          <option value="chat">Chat</option>
          <option value="code">Code</option>
          <option value="vision">Vision</option>
          <option value="tools">Tools</option>
          <option value="reasoning">Reasoning</option>
        </select>

        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--text-secondary, #d1d5db)' }}>
          <input
            type="checkbox"
            checked={localOnly}
            onChange={(e) => setLocalOnly(e.target.checked)}
          />
          Local Only
        </label>
      </div>

      {/* Models Grid */}
      {isLoading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted, #9ca3af)' }}>
          Loading canonical models catalog...
        </div>
      ) : error ? (
        <div style={{ padding: '20px', backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#f87171', borderRadius: '8px' }}>
          Failed to load models.
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '16px',
          }}
        >
          {models.map((model) => (
            <article
              key={model.id}
              onClick={() => setActiveModel(model)}
              style={{
                padding: '18px',
                borderRadius: '10px',
                backgroundColor: 'var(--bg-panel, #111827)',
                border: '1px solid var(--border-color, #1f2937)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                gap: '14px',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'rgba(59, 130, 246, 0.5)';
                e.currentTarget.style.transform = 'translateY(-2px)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-color, #1f2937)';
                e.currentTarget.style.transform = 'translateY(0)';
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      backgroundColor: 'rgba(59, 130, 246, 0.12)',
                      color: '#60a5fa',
                    }}
                  >
                    {model.vendor}
                  </span>
                  <ModelAvailability bindings={model.bindings} isActive={model.is_active} />
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
                    {model.name}
                  </h3>
                  <code style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)' }}>{model.id}</code>
                </div>
                <p
                  style={{
                    margin: 0,
                    fontSize: '0.82rem',
                    color: 'var(--text-secondary, #9ca3af)',
                    lineHeight: 1.4,
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}
                >
                  {model.description}
                </p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <ModelCapabilities capabilities={model.capabilities} isLocal={model.is_local} />
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    paddingTop: '10px',
                    borderTop: '1px solid var(--border-color, #1f2937)',
                    fontSize: '0.78rem',
                    color: 'var(--text-muted, #9ca3af)',
                  }}
                >
                  <span>
                    Context: <strong style={{ color: '#38bdf8' }}>{model.context_window >= 1000000 ? `${(model.context_window/1000000).toFixed(1)}M` : `${Math.round(model.context_window/1000)}k`}</strong>
                  </span>
                  <span>{model.bindings.length} endpoint{model.bindings.length > 1 ? 's' : ''}</span>
                </div>
              </div>
            </article>
          ))}
          {models.length === 0 && (
            <div
              style={{
                gridColumn: '1 / -1',
                padding: '40px',
                textAlign: 'center',
                color: 'var(--text-muted, #9ca3af)',
                backgroundColor: 'var(--bg-panel, #111827)',
                borderRadius: '8px',
                border: '1px dashed var(--border-color, #374151)',
              }}
            >
              No AI models found matching the search criteria.
            </div>
          )}
        </div>
      )}

      {/* Model Detail Modal */}
      {activeModel && (
        <ModelDetail model={activeModel} onClose={() => setActiveModel(null)} />
      )}
    </div>
  );
};
