/**
 * Desktop Dashboard Page (Phase 6 Cutover).
 * Delegates completely to canonical @windagent/app DashboardPage.
 * Zero synthetic data, 100% runtime telemetry backed.
 */


import { DashboardPage, type SystemMetrics } from "@windagent/app";


export type MetricState = SystemMetrics;

export interface DashboardProps {
  metrics?: any;
  setMetrics?: any;
  setActiveTab?: (tab: string) => void;
  refreshInterval?: string;
  setRefreshInterval?: (interval: string) => void;
  startNewAnalysis?: (userQuery: string) => void;
}

export function Dashboard(_props?: DashboardProps) {
  return <DashboardPage />;
}

export default Dashboard;
