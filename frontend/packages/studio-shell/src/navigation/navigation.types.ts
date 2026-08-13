import React from 'react';

export interface NavigationItemDescriptor {
  id: string;
  label: string;
  icon?: React.ReactNode;
  iconName?: string;
  route?: string;
  badge?: string;
  disabled?: boolean;
  children?: NavigationItemDescriptor[];
}

export interface NavigationGroupDescriptor {
  id: string;
  title: string;
  badge?: string;
  defaultCollapsed?: boolean;
  items: NavigationItemDescriptor[];
}
