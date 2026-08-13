import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';
import {
  AppShell,
  TopBar,
  Sidebar,
  MainWorkspace,
  BackendStatus,
  RuntimeMetrics,
  renderSparkline,
  DESKTOP_NAVIGATION_GROUPS,
} from '../index';

describe('@windagent/studio-shell package', () => {
  afterEach(cleanup);

  it('renders AppShell layout wrapper', () => {
    render(
      <AppShell header={<div data-testid="test-header">Header</div>}>
        <div data-testid="test-body">Body</div>
      </AppShell>
    );

    expect(screen.getByTestId('test-header')).toBeInTheDocument();
    expect(screen.getByTestId('test-body')).toBeInTheDocument();
  });

  it('renders TopBar with brand and custom slots', () => {
    render(
      <TopBar
        brandName="WindAgent Test"
        statusSlot={<div data-testid="test-status">Status Slot</div>}
        metricsSlot={<div data-testid="test-metrics">Metrics Slot</div>}
      />
    );

    expect(screen.getByText('WindAgent Test')).toBeInTheDocument();
    expect(screen.getByTestId('test-status')).toBeInTheDocument();
    expect(screen.getByTestId('test-metrics')).toBeInTheDocument();
  });

  it('renders BackendStatus with connected and offline indicators', () => {
    const { rerender } = render(<BackendStatus backendOnline={true} hermesOnline={true} />);
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('Hermes: Connected')).toBeInTheDocument();

    rerender(<BackendStatus backendOnline={false} hermesOnline={false} />);
    expect(screen.getByText('Backend: Offline')).toBeInTheDocument();
    expect(screen.getByText('Hermes: Offline')).toBeInTheDocument();
  });

  it('renders RuntimeMetrics with system resource sparklines', () => {
    const metrics = {
      cpu: 25,
      ram: 60,
      ramGb: 9.6,
      ramTotalGb: 16,
      gpu: 30,
      gpuName: 'NVIDIA RTX',
      vram: 40,
      vramGb: 6.4,
      vramTotalGb: 16,
      cpuHistory: [20, 22, 25],
      ramHistory: [58, 59, 60],
      gpuHistory: [28, 29, 30],
      vramHistory: [38, 39, 40],
    };

    render(<RuntimeMetrics metrics={metrics} />);

    expect(screen.getByText('25%')).toBeInTheDocument();
    expect(screen.getByText('60% 9.6 / 16 GB')).toBeInTheDocument();
  });

  it('computes sparkline points correctly', () => {
    const points = renderSparkline([10, 50, 100], 100);
    expect(points).toBe('0,12.6 25,7 50,0');
  });

  it('exports canonical desktop navigation config descriptors', () => {
    expect(DESKTOP_NAVIGATION_GROUPS.length).toBeGreaterThan(0);
    const studioGroup = DESKTOP_NAVIGATION_GROUPS.find((g) => g.id === 'studio');
    expect(studioGroup).toBeDefined();
    expect(studioGroup?.items.some((item) => item.id === 'studio')).toBe(true);
  });
});
