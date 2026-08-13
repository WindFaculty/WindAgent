import React, { useState } from 'react';
import { NavigationGroupDescriptor, NavigationItemDescriptor } from './navigation.types';

export interface NavigationGroupProps {
  group: NavigationGroupDescriptor;
  activeTab: string;
  onSelectTab: (tabId: string) => void;
}

export const NavigationGroup: React.FC<NavigationGroupProps> = ({
  group,
  activeTab,
  onSelectTab,
}) => {
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {
      models: true,
      production: !group.defaultCollapsed,
    };
    return initial;
  });

  const toggleExpand = (itemId: string) => {
    setExpandedItems((prev) => ({ ...prev, [itemId]: !prev[itemId] }));
  };

  const renderItem = (item: NavigationItemDescriptor) => {
    const hasChildren = Boolean(item.children && item.children.length > 0);
    const isChildActive = hasChildren && item.children?.some((c) => c.id === activeTab);
    const isActive = item.id === activeTab || isChildActive;
    const isExpanded = expandedItems[item.id] ?? isChildActive;

    if (hasChildren) {
      return (
        <div key={item.id} style={{ display: 'flex', flexDirection: 'column' }}>
          <div
            className={`nav-item ${isActive ? 'active' : ''}`}
            onClick={() => {
              toggleExpand(item.id);
              if (!isChildActive && item.children && item.children.length > 0) {
                onSelectTab(item.children[0].id);
              }
            }}
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {item.icon}
              <span>{item.label}</span>
              {item.badge && (
                <span className="ui-badge ui-badge--warning" style={{ fontSize: '0.65rem', padding: '1px 5px' }}>
                  {item.badge}
                </span>
              )}
            </div>
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              style={{
                transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                transition: 'transform 0.2s',
                opacity: 0.6,
              }}
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
            </svg>
          </div>

          {isExpanded && (
            <div style={{ paddingLeft: '24px', display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '2px' }}>
              {item.children?.map((child) => (
                <div
                  key={child.id}
                  className={`nav-item ${activeTab === child.id ? 'active' : ''}`}
                  onClick={() => onSelectTab(child.id)}
                  style={{ padding: '8px 12px', fontSize: '0.85rem' }}
                >
                  {child.icon}
                  <span>{child.label}</span>
                  {child.badge && (
                    <span className="ui-badge ui-badge--default" style={{ fontSize: '0.65rem', padding: '1px 5px', marginLeft: 'auto' }}>
                      {child.badge}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      );
    }

    return (
      <div
        key={item.id}
        className={`nav-item ${isActive ? 'active' : ''}`}
        onClick={() => onSelectTab(item.id)}
      >
        {item.icon}
        <span>{item.label}</span>
        {item.badge && (
          <span
            className="ui-badge ui-badge--default"
            style={{ fontSize: '0.65rem', padding: '1px 5px', marginLeft: 'auto' }}
          >
            {item.badge}
          </span>
        )}
      </div>
    );
  };

  return (
    <div className="nav-group" style={{ marginBottom: '16px' }}>
      <div
        className="nav-group-title"
        style={{
          fontSize: '0.7rem',
          fontWeight: 700,
          color: 'var(--studio-text-muted)',
          padding: '4px 12px',
          letterSpacing: '0.05em',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span>{group.title}</span>
        {group.badge && (
          <span className="ui-badge ui-badge--default" style={{ fontSize: '0.6rem', padding: '1px 4px' }}>
            {group.badge}
          </span>
        )}
      </div>
      <div className="nav-group-items">{group.items.map((item) => renderItem(item))}</div>
    </div>
  );
};

export default NavigationGroup;
