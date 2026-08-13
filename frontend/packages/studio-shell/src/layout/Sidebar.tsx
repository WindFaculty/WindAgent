import React from 'react';

export interface SidebarProps extends React.HTMLAttributes<HTMLElement> {
  footerSlot?: React.ReactNode;
}

export const Sidebar: React.FC<SidebarProps> = ({
  children,
  footerSlot,
  className = '',
  ...props
}) => {
  return (
    <aside className={`left-sidebar ${className}`.trim()} {...props}>
      <div className="sidebar-nav">{children}</div>

      {footerSlot || (
        <div className="sidebar-bottom">
          <div className="sidebar-brand-card">
            <div className="sidebar-brand-name">WindAgent</div>
            <div className="sidebar-brand-sub">Build • Create • Inspire</div>
            <svg className="sidebar-waveform" viewBox="0 0 160 30" fill="none" stroke="currentColor">
              <path d="M0 20 Q 20 5, 40 18 T 80 12 T 120 22 T 160 10" stroke="#3b82f6" strokeWidth="2" fill="none" />
            </svg>
            <div className="sidebar-env-select">
              <div className="env-select-text">
                <span className="env-title">Development</span>
                <span className="env-subtitle">Main Studio Platform</span>
              </div>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};

export default Sidebar;
