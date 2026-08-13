import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';
import { NavigationGroup } from '../navigation/NavigationGroup';
import { DESKTOP_NAVIGATION_GROUPS } from '../navigation/navigation.config';

describe('Navigation Components (UI3.1)', () => {
  afterEach(cleanup);

  it('renders navigation groups with title and items', () => {
    const handleSelect = vi.fn();
    const studioGroup = DESKTOP_NAVIGATION_GROUPS[0];

    render(
      <NavigationGroup
        group={studioGroup}
        activeTab="dashboard"
        onSelectTab={handleSelect}
      />
    );

    expect(screen.getByText('STUDIO')).toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Studio')).toBeInTheDocument();
  });

  it('handles item selection click', () => {
    const handleSelect = vi.fn();
    const studioGroup = DESKTOP_NAVIGATION_GROUPS[0];

    render(
      <NavigationGroup
        group={studioGroup}
        activeTab="dashboard"
        onSelectTab={handleSelect}
      />
    );

    fireEvent.click(screen.getByText('Studio'));
    expect(handleSelect).toHaveBeenCalledWith('studio');
  });

  it('renders status badges (e.g. BETA) on legacy items', () => {
    const handleSelect = vi.fn();
    const systemGroup = DESKTOP_NAVIGATION_GROUPS.find((g) => g.id === 'system')!;

    render(
      <NavigationGroup
        group={systemGroup}
        activeTab="agents"
        onSelectTab={handleSelect}
      />
    );

    expect(screen.getAllByText('BETA').length).toBeGreaterThan(0);
  });
});
