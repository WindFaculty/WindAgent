import { describe, it, expect } from 'vitest';
import { ResourceMetrics } from '../components/ResourceMetrics';
import { WorkerStatus } from '../components/WorkerStatus';
import { QueueMetrics } from '../components/QueueMetrics';
import { ProviderHealth } from '../components/ProviderHealth';
import { AgentMetrics } from '../components/AgentMetrics';
import { RuntimeMetrics } from '../components/RuntimeMetrics';
import { MonitoringPage } from '../pages/MonitoringPage';
import { useMonitoring, MONITORING_QUERY_KEYS } from '../hooks/useMonitoring';

describe('Monitoring Feature Components & Hooks (Phase 6)', () => {
  it('exports monitoring components and hooks properly', () => {
    expect(ResourceMetrics).toBeDefined();
    expect(WorkerStatus).toBeDefined();
    expect(QueueMetrics).toBeDefined();
    expect(ProviderHealth).toBeDefined();
    expect(AgentMetrics).toBeDefined();
    expect(RuntimeMetrics).toBeDefined();
    expect(MonitoringPage).toBeDefined();
    expect(useMonitoring).toBeDefined();
    expect(MONITORING_QUERY_KEYS.workers).toEqual(['v3', 'monitoring', 'workers']);
    expect(MONITORING_QUERY_KEYS.providers).toEqual(['v3', 'monitoring', 'providers']);
  });
});
