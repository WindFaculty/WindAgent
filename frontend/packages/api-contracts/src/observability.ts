/**
 * Observability, System Telemetry, and Dashboard Contracts (Phase 6).
 */

export interface CpuMetrics {
  usage_percent: number;
  cores_count: number;
  frequency_mhz?: number | null;
}

export interface MemoryMetrics {
  total_bytes: number;
  used_bytes: number;
  available_bytes: number;
  usage_percent: number;
}

export interface GpuMetrics {
  id: string;
  name: string;
  utilization_percent: number;
  temperature_c?: number | null;
  memory_used_bytes: number;
  memory_total_bytes: number;
}

export interface DiskMetrics {
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
  usage_percent: number;
}

export interface ProcessMetrics {
  pid: number;
  cpu_percent: number;
  memory_bytes: number;
  threads_count: number;
  uptime_seconds: number;
}

export interface SystemMetrics {
  sampled_at: string;
  cpu: CpuMetrics;
  memory: MemoryMetrics;
  gpu: GpuMetrics[];
  gpu_supported: boolean;
  disk: DiskMetrics;
  process: ProcessMetrics;
}

export interface SystemHealth {
  status: string;
  timestamp: string;
  version: string;
  checks: Record<string, string>;
}

export interface DashboardProjectsSummary {
  total: number;
  active: number;
  recent_created_count: number;
}

export interface DashboardEpisodesSummary {
  total: number;
  active: number;
  completed: number;
}

export interface DashboardRunsSummary {
  running: number;
  failed: number;
  succeeded: number;
  total: number;
}

export interface DashboardAgentsSummary {
  total: number;
  running: number;
  idle: number;
  active_roles: string[];
}

export interface DashboardProvidersSummary {
  total: number;
  healthy: number;
}

export interface ActivityDataPoint {
  timestamp: string;
  label: string;
  ideas_count: number;
  outlines_count: number;
  scripts_count: number;
  renders_count: number;
  total_activity: number;
}

export interface ModelUsageStat {
  model_id: string;
  name: string;
  provider: string;
  usage_percent: number;
  tokens_per_second: number;
  latency_ms: number;
}

export interface StorageSummary {
  workspace_used_bytes: number;
  workspace_total_bytes: number;
  assets_count: number;
}

export interface RecentActivityItem {
  id: string;
  type: string;
  title: string;
  timestamp: string;
  status: string;
  metadata?: Record<string, unknown>;
}

export interface DashboardSummary {
  sampled_at: string;
  projects: DashboardProjectsSummary;
  episodes: DashboardEpisodesSummary;
  runs: DashboardRunsSummary;
  agents: DashboardAgentsSummary;
  providers: DashboardProvidersSummary;
  activity_by_timeframe: Record<string, ActivityDataPoint[]>;
  model_usage: ModelUsageStat[];
  storage: StorageSummary;
  recent_activities: RecentActivityItem[];
}

export interface WorkerInfo {
  worker_id: string;
  name: string;
  status: 'active' | 'idle' | 'busy' | 'stopped' | string;
  current_job_id?: string | null;
  concurrency: number;
  uptime_seconds: number;
}

export interface WorkersMonitoringResponse {
  workers: WorkerInfo[];
  total_workers: number;
  active_workers: number;
}

export interface ProviderMonitoringInfo {
  provider_id: string;
  name: string;
  status: 'healthy' | 'degraded' | 'unreachable' | string;
  avg_latency_ms: number;
  error_rate_percent: number;
  total_requests: number;
}

export interface ProvidersMonitoringResponse {
  providers: ProviderMonitoringInfo[];
}

export interface AgentMonitoringInfo {
  agent_id: string;
  name: string;
  role: string;
  status: 'running' | 'idle' | 'busy' | string;
  current_task?: string | null;
  tasks_completed: number;
  avg_turn_ms: number;
}

export interface AgentsMonitoringResponse {
  agents: AgentMonitoringInfo[];
}

export interface QueueMonitoringInfo {
  queue_name: string;
  depth: number;
  in_flight: number;
  throughput_per_sec: number;
}

export interface QueuesMonitoringResponse {
  queues: QueueMonitoringInfo[];
}

export interface RunMonitoringInfo {
  run_id: string;
  run_type: string;
  status: 'running' | 'succeeded' | 'failed' | 'cancelled' | string;
  started_at: string;
  duration_ms?: number | null;
  initiator: string;
}

export interface RunsMonitoringResponse {
  runs: RunMonitoringInfo[];
}
