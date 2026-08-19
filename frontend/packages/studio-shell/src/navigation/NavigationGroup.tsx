import React, { useState } from 'react';
import { NavigationGroupDescriptor, NavigationItemDescriptor } from './navigation.types';

export const renderNavIcon = (icon?: React.ReactNode, iconName?: string, id?: string): React.ReactNode => {
  if (icon) return icon;
  const name = (iconName || id || '').toLowerCase();

  switch (name) {
    case 'layoutdashboard':
    case 'dashboard':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="7" height="9" rx="1" />
          <rect x="14" y="3" width="7" height="5" rx="1" />
          <rect x="14" y="12" width="7" height="9" rx="1" />
          <rect x="3" y="16" width="7" height="5" rx="1" />
        </svg>
      );
    case 'clapperboard':
    case 'studio':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.4-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.4Z" />
          <path d="m6.2 5.3 3.1 3.9M12.4 3.4l3.1 4M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
        </svg>
      );
    case 'folder':
    case 'projects':
    case 'files':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
        </svg>
      );
    case 'film':
    case 'episodes':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2" />
          <path d="M7 3v18M17 3v18M3 7.5h4M3 12h18M3 16.5h4M17 7.5h4M17 16.5h4" />
        </svg>
      );
    case 'layoutgrid':
    case 'storyboard':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="7" height="7" x="3" y="3" rx="1" />
          <rect width="7" height="7" x="14" y="3" rx="1" />
          <rect width="7" height="7" x="14" y="14" rx="1" />
          <rect width="7" height="7" x="3" y="14" rx="1" />
        </svg>
      );
    case 'users':
    case 'characters':
    case 'agents':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );
    case 'globe':
    case 'world':
    case 'browser':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 2a14.5 14.5 0 0 0 0 20M2 12h20" />
        </svg>
      );
    case 'package':
    case 'assets':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m7.5 4.27 9 5.15M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
          <path d="m3.3 7 8.7 5 8.7-5M12 22V12" />
        </svg>
      );
    case 'checksquare':
    case 'reviews':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m9 11 3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
      );
    case 'video':
    case 'live-record':
    case 'liverecord':
    case 'record':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m22 8-6 4 6 4V8Z" />
          <rect width="14" height="12" x="2" y="6" rx="2" />
        </svg>
      );
    case 'bot':
    case 'workspace':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 8V4H8" />
          <rect width="16" height="12" x="4" y="8" rx="2" />
          <path d="M2 14h2M20 14h2M15 13v2M9 13v2" />
        </svg>
      );
    case 'server':
    case 'router':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="20" height="8" x="2" y="2" rx="2" />
          <rect width="20" height="8" x="2" y="14" rx="2" />
          <line x1="6" x2="6.01" y1="6" y2="6" />
          <line x1="6" x2="6.01" y1="18" y2="18" />
        </svg>
      );
    case 'settings':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      );
    case 'gitbranch':
    case 'workflows':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="6" x2="6" y1="3" y2="15" />
          <circle cx="18" cy="6" r="3" />
          <circle cx="6" cy="18" r="3" />
          <path d="M18 9a9 9 0 0 1-9 9" />
        </svg>
      );
    case 'activity':
    case 'monitoring':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
      );
    case 'filetext':
    case 'logs':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
          <path d="M14 2v4a2 2 0 0 0 2 2h4M10 9H8M16 13H8M16 17H8" />
        </svg>
      );
    case 'database':
    case 'memory':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M3 5V19A9 3 0 0 0 21 19V5" />
          <path d="M3 12A9 3 0 0 0 21 12" />
        </svg>
      );
    default:
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
        </svg>
      );
  }
};

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
              {renderNavIcon(item.icon, item.iconName, item.id)}
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
                  {renderNavIcon(child.icon, child.iconName, child.id)}
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
        {renderNavIcon(item.icon, item.iconName, item.id)}
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
