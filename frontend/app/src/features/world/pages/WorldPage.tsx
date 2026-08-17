/**
 * Phase 9B — WorldPage
 * Canonical World Bible UI backed by /api/v3/projects/{id}/world.
 */
import React, { useState } from 'react';
import { useWorldBible, useLocations, useFactions, useLore, useCreateLocation, useCreateFaction, useCreateLore } from '../hooks/useWorld';

interface WorldPageProps {
  projectId: string;
}

type WorldTab = 'overview' | 'locations' | 'factions' | 'lore';

export const WorldPage: React.FC<WorldPageProps> = ({ projectId }) => {
  const [activeTab, setActiveTab] = useState<WorldTab>('overview');

  const { data: worldBible, isLoading: loadingBible } = useWorldBible(projectId);
  const { data: locations = [], isLoading: loadingLocs } = useLocations(projectId);
  const { data: factions = [], isLoading: loadingFacs } = useFactions(projectId);
  const { data: lore = [], isLoading: loadingLore } = useLore(projectId);

  const createLocation = useCreateLocation(projectId);
  const createFaction = useCreateFaction(projectId);
  const createLore = useCreateLore(projectId);

  const isLoading = loadingBible || loadingLocs || loadingFacs || loadingLore;

  if (isLoading) {
    return (
      <div className="world-page world-page--loading">
        <div className="loading-spinner" />
        <p>Đang tải World Bible...</p>
      </div>
    );
  }

  const tabs: { id: WorldTab; label: string; count?: number }[] = [
    { id: 'overview', label: '🌍 Tổng quan' },
    { id: 'locations', label: '📍 Địa điểm', count: locations.length },
    { id: 'factions', label: '⚔️ Phe phái', count: factions.length },
    { id: 'lore', label: '📖 Lịch sử & Lore', count: lore.length },
  ];

  return (
    <div className="world-page">
      <header className="world-page__header">
        <div className="world-page__title-row">
          <h1>{worldBible?.world_name ?? 'World Bible'}</h1>
          {worldBible?.timeline_era && <span className="world-page__era">{worldBible.timeline_era}</span>}
        </div>
        {worldBible?.setting_summary && <p className="world-page__summary">{worldBible.setting_summary}</p>}
      </header>

      <nav className="world-page__tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`world-page__tab${activeTab === tab.id ? ' world-page__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.count !== undefined && <span className="world-page__tab-count">{tab.count}</span>}
          </button>
        ))}
      </nav>

      <div className="world-page__content">
        {activeTab === 'overview' && worldBible && (
          <div className="world-overview">
            {worldBible.core_theme && (
              <div className="world-overview__section">
                <h3>Chủ đề cốt lõi</h3>
                <p>{worldBible.core_theme}</p>
              </div>
            )}
            {worldBible.rules.length > 0 && (
              <div className="world-overview__section">
                <h3>Quy tắc thế giới</h3>
                <ul className="world-overview__rules">
                  {worldBible.rules.map((rule, i) => (
                    <li key={i}>{rule}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="world-overview__stats">
              <div className="world-stat">
                <span className="world-stat__value">{worldBible.locations_count}</span>
                <span className="world-stat__label">Địa điểm</span>
              </div>
              <div className="world-stat">
                <span className="world-stat__value">{worldBible.factions_count}</span>
                <span className="world-stat__label">Phe phái</span>
              </div>
              <div className="world-stat">
                <span className="world-stat__value">{worldBible.lore_count}</span>
                <span className="world-stat__label">Lore</span>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'locations' && (
          <div className="world-entity-list">
            <div className="world-entity-list__header">
              <h3>Địa điểm ({locations.length})</h3>
              <button
                className="btn btn--primary btn--sm"
                onClick={() => createLocation.mutate({ name: 'Địa điểm mới', description: '' })}
                disabled={createLocation.isPending}
              >
                + Thêm
              </button>
            </div>
            {locations.length === 0 ? (
              <p className="world-entity-list__empty">Chưa có địa điểm. Hãy thêm địa điểm đầu tiên.</p>
            ) : (
              <div className="world-entity-grid">
                {locations.map((loc) => (
                  <div key={loc.id} className="world-entity-card">
                    <div className="world-entity-card__type">{loc.type}</div>
                    <h4>{loc.name}</h4>
                    <p>{loc.description}</p>
                    {loc.atmosphere && <div className="world-entity-card__tag">🎭 {loc.atmosphere}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'factions' && (
          <div className="world-entity-list">
            <div className="world-entity-list__header">
              <h3>Phe phái ({factions.length})</h3>
              <button
                className="btn btn--primary btn--sm"
                onClick={() => createFaction.mutate({ name: 'Phe phái mới' })}
                disabled={createFaction.isPending}
              >
                + Thêm
              </button>
            </div>
            {factions.length === 0 ? (
              <p className="world-entity-list__empty">Chưa có phe phái. Hãy thêm phe phái đầu tiên.</p>
            ) : (
              <div className="world-entity-grid">
                {factions.map((fac) => (
                  <div key={fac.id} className="world-entity-card">
                    <div className="world-entity-card__influence">
                      <span style={{ width: `${fac.influence_level}%` }} />
                    </div>
                    <h4>{fac.name}</h4>
                    <p className="world-entity-card__ideology">{fac.ideology}</p>
                    <p>{fac.description}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'lore' && (
          <div className="world-entity-list">
            <div className="world-entity-list__header">
              <h3>Lịch sử & Lore ({lore.length})</h3>
              <button
                className="btn btn--primary btn--sm"
                onClick={() => createLore.mutate({ title: 'Sự kiện mới', category: 'History', content: '' })}
                disabled={createLore.isPending}
              >
                + Thêm
              </button>
            </div>
            {lore.length === 0 ? (
              <p className="world-entity-list__empty">Chưa có lore. Hãy thêm sự kiện đầu tiên.</p>
            ) : (
              <div className="world-lore-list">
                {lore.map((entry) => (
                  <div key={entry.id} className="world-lore-entry">
                    <div className="world-lore-entry__header">
                      <h4>{entry.title}</h4>
                      <span className="world-lore-entry__category">{entry.category}</span>
                    </div>
                    <p>{entry.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
