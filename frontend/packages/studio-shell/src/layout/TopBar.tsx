import React, { useState } from 'react';

export interface TopBarProps extends React.HTMLAttributes<HTMLElement> {
  brandName?: string;
  brandIcon?: React.ReactNode;
  statusSlot?: React.ReactNode;
  metricsSlot?: React.ReactNode;
  actionsSlot?: React.ReactNode;
  activeNavTab?: string;
  onNavTabChange?: (tab: string) => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  brandName = 'WindAgent Studio',
  brandIcon,
  statusSlot,
  metricsSlot,
  actionsSlot,
  activeNavTab = 'studio',
  onNavTabChange,
  className = '',
  ...props
}) => {
  const [selectedTab, setSelectedTab] = useState(activeNavTab);

  const handleTabClick = (tabId: string) => {
    setSelectedTab(tabId);
    if (onNavTabChange) onNavTabChange(tabId);
  };

  const navTabs = [
    {
      id: 'studio',
      label: 'Studio',
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="2" y="4" width="20" height="16" rx="2" />
          <path d="M7 4v16M17 4v16M2 8h20M2 16h20" />
        </svg>
      ),
    },
    {
      id: 'assets',
      label: 'Assets',
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
        </svg>
      ),
    },
    {
      id: 'models',
      label: 'Models',
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <rect x="9" y="9" width="6" height="6" />
          <path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3" />
        </svg>
      ),
    },
    {
      id: 'monitoring',
      label: 'Monitoring',
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v6l4 2" />
        </svg>
      ),
    },
    {
      id: 'settings',
      label: 'Settings',
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      ),
    },
  ];

  return (
    <header className={`top-header ${className}`.trim()} {...props}>
      <div className="header-left">
        <div className="brand">
          {brandIcon || (
            <svg
              className="brand-icon"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2.5}
                d="M4.5 12a7.5 7.5 0 0015 0m-15 0a7.5 7.5 0 1115 0m-15 0H3m16.5 0H21m-1.5 0H12m-8.457 3.077l1.41-.513m14.095-5.128l1.41-.513M5.106 17.785l1.15-.827m11.488-8.226l1.15-.827M8.14 21.27l.707-1.03m10.15-6.83l.707-1.03"
              />
            </svg>
          )}
          <span className="brand-title">{brandName}</span>
        </div>
      </div>

      <div className="header-center-nav">
        {navTabs.map((tab) => (
          <button
            key={tab.id}
            className={`top-nav-pill ${selectedTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabClick(tab.id)}
          >
            <span className="pill-icon">{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="header-right">
        {statusSlot || (
          <div className="topbar-status-indicator">
            <span className="status-dot-green"></span>
            <span className="status-label-text">System Online</span>
          </div>
        )}

        <span className="version-badge-pill">v0.1.0-dev</span>

        <div className="user-profile-pill">
          <div className="avatar-circle">TK</div>
          <span className="user-name-text">Tran Xuan Khoa</span>
          <svg className="chevron-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>

        {metricsSlot}

        {actionsSlot}
      </div>
    </header>
  );
};

export default TopBar;
