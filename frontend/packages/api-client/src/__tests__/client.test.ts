import { describe, it, expect, vi } from 'vitest';
import { WindAgentClient, createApiClient } from '../client';
import { ApiError } from '../errors';

describe('WindAgentClient API Façade', () => {
  it('instantiates all domain API facades correctly', () => {
    const client = createApiClient({ baseUrl: 'http://localhost:8000' });
    expect(client).toBeInstanceOf(WindAgentClient);
    expect(client.projects).toBeDefined();
    expect(client.episodes).toBeDefined();
    expect(client.studio).toBeDefined();
    expect(client.agents).toBeDefined();
    expect(client.assets).toBeDefined();
    expect(client.system).toBeDefined();
    expect(client.transport).toBeDefined();
  });

  describe('projects API', () => {
    it('calls GET /api/v3/projects for list()', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          items: [{ id: 'proj_1', name: 'Project 1', version: 1, created_at: '2026-01-01', updated_at: '2026-01-01' }],
          page_info: { next_cursor: null, has_more: false },
        }),
      });

      const client = new WindAgentClient({ baseUrl: 'http://localhost:8000', fetchImpl: mockFetch as any });
      const result = await client.projects.list('cursor_abc');

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('/api/v3/projects');
      expect(url).toContain('cursor=cursor_abc');
      expect(result.items).toHaveLength(1);
      expect(result.items[0].id).toBe('proj_1');
    });

    it('calls POST /api/v3/projects with Idempotency-Key for create()', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          id: 'proj_new',
          name: 'New Show',
          version: 1,
          created_at: '2026-01-01',
          updated_at: '2026-01-01',
        }),
      });

      const client = new WindAgentClient({ baseUrl: 'http://localhost:8000', fetchImpl: mockFetch as any });
      const created = await client.projects.create({ name: 'New Show', description: 'Test' }, 'idem_123');

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, init] = mockFetch.mock.calls[0];
      expect(url).toContain('/api/v3/projects');
      expect(init.method).toBe('POST');
      expect(init.headers['Idempotency-Key']).toBe('idem_123');
      expect(JSON.parse(init.body)).toEqual({ name: 'New Show', description: 'Test' });
      expect(created.id).toBe('proj_new');
    });

    it('calls PATCH /api/v3/projects/:id with expected_version for update()', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          id: 'proj_1',
          name: 'Updated Show',
          version: 2,
          created_at: '2026-01-01',
          updated_at: '2026-01-02',
        }),
      });

      const client = new WindAgentClient({ baseUrl: 'http://localhost:8000', fetchImpl: mockFetch as any });
      const updated = await client.projects.update('proj_1', { name: 'Updated Show', expected_version: 1 }, 'idem_patch');

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, init] = mockFetch.mock.calls[0];
      expect(url).toContain('/api/v3/projects/proj_1');
      expect(init.method).toBe('PATCH');
      expect(init.headers['Idempotency-Key']).toBe('idem_patch');
      expect(JSON.parse(init.body)).toEqual({ name: 'Updated Show', expected_version: 1 });
      expect(updated.version).toBe(2);
    });
  });

  describe('episodes API', () => {
    it('lists and gets episodes correctly', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          id: 'ep_1',
          project_id: 'proj_1',
          title: 'Pilot',
          version: 1,
          created_at: '2026-01-01',
          updated_at: '2026-01-01',
        }),
      });

      const client = new WindAgentClient({ baseUrl: 'http://localhost:8000', fetchImpl: mockFetch as any });
      const ep = await client.episodes.get('proj_1', 'ep_1');

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('/api/v3/projects/proj_1/episodes/ep_1');
      expect(ep.title).toBe('Pilot');
    });
  });

  describe('studio API', () => {
    it('retrieves capabilities and readiness snapshots', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          status: 'READY',
          capabilities: { story_engine: 'AVAILABLE', worker: 'AVAILABLE' },
          fail_closed_flags: [],
          certification_mode: 'STRICT',
        }),
      });

      const client = new WindAgentClient({ baseUrl: 'http://localhost:8000', fetchImpl: mockFetch as any });
      const readiness = await client.studio.getReadiness();

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('/api/v3/studio/readiness');
      expect(readiness.status).toBe('READY');
    });
  });

  describe('agents and assets API', () => {
    it('executes agent task with command receipt', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 202,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          command_id: 'cmd_123',
          status: 'ACCEPTED',
          resource_id: 'inst_1',
          correlation_id: 'corr_456',
          submitted_at: '2026-01-01T00:00:00Z',
        }),
      });

      const client = new WindAgentClient({ baseUrl: 'http://localhost:8000', fetchImpl: mockFetch as any });
      const receipt = await client.agents.executeTask('inst_1', { task: 'Analyze Script' }, 'idem_exec');

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, init] = mockFetch.mock.calls[0];
      expect(url).toContain('/api/v3/agents/instances/inst_1/execute');
      expect(init.headers['Idempotency-Key']).toBe('idem_exec');
      expect(receipt.status).toBe('ACCEPTED');
      expect(receipt.command_id).toBe('cmd_123');
    });

    it('retrieves assets by id', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          id: 'asset_789',
          project_id: 'proj_1',
          type: 'MODEL_3D',
          name: 'Hero 3D Mesh',
          status: 'DRAFT',
          provenance: { source: 'generation', job_id: 'job_1' },
          version: 1,
          created_at: '2026-01-01',
          updated_at: '2026-01-01',
        }),
      });

      const client = new WindAgentClient({ baseUrl: 'http://localhost:8000', fetchImpl: mockFetch as any });
      const asset = await client.assets.get('asset_789');

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('/api/v3/assets/asset_789');
      expect(asset.type).toBe('MODEL_3D');
    });
  });

  describe('system API & correlation ID propagation', () => {
    it('propagates correlation id header across requests', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ status: 'healthy' }),
      });

      const client = new WindAgentClient({
        baseUrl: 'http://localhost:8000',
        fetchImpl: mockFetch as any,
        getCorrelationId: () => 'req-trace-uuid-999',
      });

      const health = await client.system.getHealth();
      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, init] = mockFetch.mock.calls[0];
      expect(url).toContain('/health');
      expect(init.headers['X-Correlation-ID']).toBe('req-trace-uuid-999');
      expect(health.status).toBe('healthy');
    });

    it('fetches system metrics and health', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          sampled_at: '2026-01-01T00:00:00Z',
          cpu: { usage_percent: 24.5, cores_count: 8 },
          memory: { total_bytes: 16000000, used_bytes: 8000000, available_bytes: 8000000, usage_percent: 50.0 },
          gpu: [],
          gpu_supported: false,
          disk: { total_bytes: 500000000, used_bytes: 200000000, free_bytes: 300000000, usage_percent: 40.0 },
          process: { pid: 1234, cpu_percent: 2.1, memory_bytes: 150000000, threads_count: 12, uptime_seconds: 120.0 },
        }),
      });

      const client = new WindAgentClient({ baseUrl: 'http://localhost:8000', fetchImpl: mockFetch as any });
      const metrics = await client.system.getMetrics();

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('/api/v3/system/metrics');
      expect(metrics.cpu.usage_percent).toBe(24.5);
      expect(metrics.gpu_supported).toBe(false);
    });
  });


  describe('dashboard & monitoring API', () => {
    it('retrieves dashboard summary', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          sampled_at: '2026-01-01T00:00:00Z',
          projects: { total: 4, active: 3, recent_created_count: 2 },
          episodes: { total: 14, active: 5, completed: 9 },
          runs: { running: 1, failed: 0, succeeded: 28, total: 29 },
          agents: { total: 6, running: 4, idle: 2, active_roles: ['Story Architect'] },
          providers: { total: 4, healthy: 4 },
          activity_by_timeframe: {},
          model_usage: [],
          storage: { workspace_used_bytes: 500000, workspace_total_bytes: 10000000, assets_count: 10 },
          recent_activities: [],
        }),
      });

      const client = new WindAgentClient({ baseUrl: 'http://localhost:8000', fetchImpl: mockFetch as any });
      const summary = await client.dashboard.getSummary();

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('/api/v3/dashboard/summary');
      expect(summary.projects.total).toBe(4);
      expect(summary.episodes.total).toBe(14);
    });

    it('retrieves monitoring workers, providers, agents, queues, and runs', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          workers: [{ worker_id: 'wrk-1', name: 'Core', status: 'active', concurrency: 2, uptime_seconds: 100 }],
          total_workers: 1,
          active_workers: 1,
        }),
      });

      const client = new WindAgentClient({ baseUrl: 'http://localhost:8000', fetchImpl: mockFetch as any });
      const workers = await client.monitoring.getWorkers();

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(workers.total_workers).toBe(1);
      expect(workers.workers[0].worker_id).toBe('wrk-1');
    });
  });
});

