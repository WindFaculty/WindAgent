import React from 'react';

export interface TabItem {
  id: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  disabled?: boolean;
}

export interface TabsProps {
  tabs?: TabItem[];
  items?: TabItem[];
  activeTab?: string;
  activeId?: string;
  onChange: (id: string) => void;
  className?: string;
}

export const Tabs: React.FC<TabsProps> = ({
  tabs,
  items,
  activeTab,
  activeId,
  onChange,
  className = '',
}) => {
  const tabList = tabs || items || [];
  const currentActive = activeTab || activeId;

  return (
    <div className={`ui-tabs-list ${className}`.trim()} role="tablist">
      {tabList.map((tab) => {
        const isActive = tab.id === currentActive;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            disabled={tab.disabled}
            data-active={String(isActive)}
            className="ui-tab-trigger"
            onClick={() => onChange(tab.id)}
          >
            {tab.icon && <span style={{ marginRight: 6 }}>{tab.icon}</span>}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
};

export default Tabs;
