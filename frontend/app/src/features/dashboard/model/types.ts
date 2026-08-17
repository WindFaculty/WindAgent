/**
 * Dashboard Types and State Interfaces (Phase 6).
 */

import type {
  DashboardSummary,
  SystemMetrics,
  ActivityDataPoint,
  ModelUsageStat,
  RecentActivityItem,
} from '@windagent/api-contracts';

export type {
  DashboardSummary,
  SystemMetrics,
  ActivityDataPoint,
  ModelUsageStat,
  RecentActivityItem,
};

export type ActivityTimeframe = '24h' | '7d' | '30d' | '90d';

export interface SystemMetricHistory {
  cpu: number[];
  ram: number[];
  gpu: number[];
  vram: number[];
}
