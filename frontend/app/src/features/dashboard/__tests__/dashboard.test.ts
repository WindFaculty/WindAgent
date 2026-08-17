import { describe, it, expect } from 'vitest';
import { StudioSummaryCards } from '../components/StudioSummaryCards';
import { StudioActivityChart } from '../components/StudioActivityChart';
import { ModelUsagePanel } from '../components/ModelUsagePanel';
import { DashboardPage } from '../pages/DashboardPage';
import { useDashboardSummary, DASHBOARD_SUMMARY_QUERY_KEY } from '../hooks/useDashboardSummary';
import { useSystemMetrics } from '../hooks/useSystemMetrics';

describe('Dashboard Feature Components & Hooks (Phase 6)', () => {
  it('exports dashboard components and hooks properly', () => {
    expect(StudioSummaryCards).toBeDefined();
    expect(StudioActivityChart).toBeDefined();
    expect(ModelUsagePanel).toBeDefined();
    expect(DashboardPage).toBeDefined();
    expect(useDashboardSummary).toBeDefined();
    expect(useSystemMetrics).toBeDefined();
    expect(DASHBOARD_SUMMARY_QUERY_KEY).toEqual(['v3', 'dashboard', 'summary']);
  });
});
