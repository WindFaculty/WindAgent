import React, { useState } from 'react';
import { ProductionActivity, ActivityCategory } from '@windagent/production-contracts';

export interface ActivityTimelinePanelProps {
  activities: ProductionActivity[];
  onEntityClick?: (entityId: string, entityType: string) => void;
  isLoading?: boolean;
}

export const ActivityTimelinePanel: React.FC<ActivityTimelinePanelProps> = ({
  activities,
  onEntityClick,
  isLoading = false,
}) => {
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');

  const filteredActivities = activities.filter((a) => {
    if (categoryFilter === 'ALL') return true;
    return a.category === categoryFilter;
  });

  const getCategoryBadgeStyle = (category: ActivityCategory) => {
    switch (category) {
      case 'SCRIPT':
        return { background: '#3b82f622', color: '#60a5fa', border: '1px solid #3b82f644' };
      case 'ASSET':
      case 'BINDING':
        return { background: '#10b98122', color: '#34d399', border: '1px solid #10b98144' };
      case 'PROPOSAL':
        return { background: '#f59e0b22', color: '#fbbf24', border: '1px solid #f59e0b44' };
      case 'JOB':
        return { background: '#8b5cf622', color: '#a78bfa', border: '1px solid #8b5cf644' };
      default:
        return { background: '#64748b22', color: '#94a3b8', border: '1px solid #64748b44' };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0f172a', color: '#f8fafc', borderRadius: 8, overflow: 'hidden', border: '1px solid #1e293b' }}>
      {/* Header & Category Filters */}
      <div style={{ padding: 16, borderBottom: '1px solid #1e293b', background: '#090d16', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Production Activity Timeline</h3>
          <p style={{ margin: '2px 0 0 0', fontSize: 12, color: '#94a3b8' }}>Realtime Activity Feed (UI38)</p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {['ALL', 'SCRIPT', 'ASSET', 'BINDING', 'PROPOSAL', 'JOB', 'SYSTEM'].map((cat) => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              style={{
                padding: '4px 10px',
                borderRadius: 4,
                fontSize: 11,
                fontWeight: 500,
                cursor: 'pointer',
                border: 'none',
                background: categoryFilter === cat ? '#3b82f6' : '#1e293b',
                color: categoryFilter === cat ? '#ffffff' : '#94a3b8',
              }}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Activity Timeline List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
        {isLoading ? (
          <div style={{ textAlign: 'center', color: '#94a3b8', padding: 24, fontSize: 13 }}>Loading activity timeline...</div>
        ) : filteredActivities.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#64748b', padding: 24, fontSize: 13 }}>No production activities recorded.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {filteredActivities.map((act) => {
              const catBadge = getCategoryBadgeStyle(act.category);
              return (
                <div
                  key={act.activity_id}
                  style={{
                    padding: 12,
                    borderRadius: 6,
                    background: '#1e293b',
                    border: '1px solid #334155',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, ...catBadge }}>
                        {act.category}
                      </span>
                      <strong style={{ fontSize: 13, color: '#f8fafc' }}>{act.title}</strong>
                    </div>
                    <span style={{ fontSize: 11, color: '#64748b' }}>
                      {new Date(act.occurred_at).toLocaleTimeString()}
                    </span>
                  </div>

                  <div style={{ fontSize: 12, color: '#cbd5e1', lineHeight: '1.4' }}>
                    {act.summary}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4, paddingTop: 4, borderTop: '1px solid #334155' }}>
                    <div style={{ fontSize: 11, color: '#94a3b8', display: 'flex', gap: 12 }}>
                      <span>Actor: <code style={{ color: '#38bdf8' }}>{act.actor}</code></span>
                      <span>Rev: <code style={{ color: '#a5f3fc' }}>{act.revision_id}</code></span>
                    </div>

                    {/* Entity Links */}
                    {act.entity_links.length > 0 && (
                      <div style={{ display: 'flex', gap: 6 }}>
                        {act.entity_links.map((link) => (
                          <button
                            key={link.entity_id}
                            onClick={() => onEntityClick && onEntityClick(link.entity_id, link.entity_type)}
                            style={{
                              padding: '2px 8px',
                              borderRadius: 4,
                              background: '#020617',
                              border: '1px solid #3b82f6',
                              color: '#60a5fa',
                              fontSize: 10,
                              cursor: 'pointer',
                            }}
                          >
                            🔗 {link.display_name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
