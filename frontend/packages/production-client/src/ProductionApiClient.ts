import {
  ProductionProject,
  ProductionRevision,
  WorkspaceSnapshot,
  WorkspaceCommandRequest,
  WorkspaceCommandResult,
  ProductionEventEnvelope,
  ProblemDetails,
} from '@windagent/production-contracts';

export type SyncState = 'CONNECTED' | 'RECONNECTING' | 'REPLAYING' | 'STALE' | 'OFFLINE';

export interface ProductionApiClient {
  getProject(id: string): Promise<ProductionProject | null>;
  listProjects(): Promise<ProductionProject[]>;
  getLatestRevision(projectId: string): Promise<ProductionRevision | null>;
  getWorkspaceSnapshot(projectId: string, revisionId?: string): Promise<WorkspaceSnapshot>;
  executeCommand(
    request: WorkspaceCommandRequest,
    idempotencyKey?: string
  ): Promise<WorkspaceCommandResult>;
}

export class HttpProductionApiClient implements ProductionApiClient {
  constructor(private baseUrl: string = 'http://localhost:8000') {}

  async getProject(id: string): Promise<ProductionProject | null> {
    const res = await fetch(`${this.baseUrl}/api/v3/production/projects/${id}`);
    if (res.status === 404) return null;
    if (!res.ok) {
      throw new Error(`Failed to fetch project details: ${res.statusText}`);
    }
    const data = await res.json();
    return {
      id: data.id,
      name: data.name,
      status: data.status,
      active_revision_id: data.active_revision_id,
      createdAt: data.created_at,
      updatedAt: data.updated_at,
    };
  }

  async listProjects(): Promise<ProductionProject[]> {
    const p = await this.getProject('vp_001');
    return p ? [p] : [];
  }

  async getLatestRevision(projectId: string): Promise<ProductionRevision | null> {
    const p = await this.getProject(projectId);
    if (!p) return null;
    return {
      id: p.active_revision_id || `rev-${projectId}-v1`,
      projectId,
      sequenceNumber: 1,
      status: 'draft',
      createdAt: new Date().toISOString(),
    };
  }

  async getWorkspaceSnapshot(projectId: string, revisionId?: string): Promise<WorkspaceSnapshot> {
    let url = `${this.baseUrl}/api/v3/production/projects/${projectId}/workspace`;
    if (revisionId) {
      url += `?revision_id=${encodeURIComponent(revisionId)}`;
    }
    const res = await fetch(url);
    if (res.status === 409) {
      const problem: ProblemDetails = (await res.json()).detail || {};
      throw new Error(`STALE_REVISION: ${problem.detail || 'Target revision is stale'}`);
    }
    if (!res.ok) {
      throw new Error(`Failed to fetch workspace snapshot: ${res.statusText}`);
    }
    return (await res.json()) as WorkspaceSnapshot;
  }

  async executeCommand(
    request: WorkspaceCommandRequest,
    idempotencyKey?: string
  ): Promise<WorkspaceCommandResult> {
    const key = idempotencyKey || `key_${Math.random().toString(36).substring(2, 11)}`;
    const res = await fetch(`${this.baseUrl}/api/v3/production/commands`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Idempotency-Key': key,
      },
      body: JSON.stringify(request),
    });

    if (res.status === 409) {
      const problem: ProblemDetails = (await res.json()).detail || {};
      return {
        command_id: `cmd_conflict_${Date.now()}`,
        status: (problem.code as any) || 'REJECTED_STALE',
        updated_revision_id: problem.current_revision_id || request.target_revision_id,
        message: problem.detail || 'Command rejected due to conflict',
        current_sequence: problem.current_sequence || 0,
      };
    }

    if (!res.ok) {
      throw new Error(`Command execution failed: ${res.statusText}`);
    }

    return (await res.json()) as WorkspaceCommandResult;
  }
}

export class FakeProductionApiClient implements ProductionApiClient {
  private projects: ProductionProject[] = [
    {
      id: 'proj-alpha',
      name: 'Alpha Production Project',
      description: 'Default baseline production workspace project',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
    {
      id: 'proj-beta',
      name: 'Beta Sci-Fi Project',
      description: 'Cyberpunk short film production fixture',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
  ];

  private currentSequence = 10;
  private idempotencyStore = new Map<string, WorkspaceCommandResult>();

  async getProject(id: string): Promise<ProductionProject | null> {
    return this.projects.find((p) => p.id === id) || null;
  }

  async listProjects(): Promise<ProductionProject[]> {
    return [...this.projects];
  }

  async getLatestRevision(projectId: string): Promise<ProductionRevision | null> {
    const project = await this.getProject(projectId);
    if (!project) return null;

    return {
      id: `rev-${projectId}-v1`,
      projectId,
      sequenceNumber: this.currentSequence,
      status: 'draft',
      createdAt: new Date().toISOString(),
    };
  }

  async getWorkspaceSnapshot(projectId: string, revisionId?: string): Promise<WorkspaceSnapshot> {
    const project = await this.getProject(projectId);
    if (!project) {
      throw new Error(`Project ${projectId} not found`);
    }

    const currentRev = `rev-${projectId}-v1`;
    if (revisionId && revisionId !== currentRev) {
      throw new Error(`STALE_REVISION: Requested '${revisionId}', current is '${currentRev}'`);
    }

    return {
      project_id: projectId,
      revision_id: currentRev,
      project_status: 'ACTIVE',
      revision_status: 'DRAFT',
      creative_brief_locked: true,
      screenplay_locked: false,
      total_shots: 6,
      candidates_count: 12,
      current_sequence: this.currentSequence,
      authorized_media_urls: {
        shot_01: '/media/tok_shot_01',
      },
    };
  }

  async executeCommand(
    request: WorkspaceCommandRequest,
    idempotencyKey?: string
  ): Promise<WorkspaceCommandResult> {
    const key = idempotencyKey || 'default_key';
    if (this.idempotencyStore.has(key)) {
      return this.idempotencyStore.get(key)!;
    }

    const currentRev = `rev-${request.project_id}-v1`;
    if (request.target_revision_id !== currentRev) {
      const conflict: WorkspaceCommandResult = {
        command_id: `cmd_${Date.now()}`,
        status: 'REJECTED_STALE',
        updated_revision_id: currentRev,
        message: `Target revision '${request.target_revision_id}' is stale. Server is at '${currentRev}'`,
        current_sequence: this.currentSequence,
      };
      this.idempotencyStore.set(key, conflict);
      return conflict;
    }

    this.currentSequence += 1;
    const newRev = `rev-${request.project_id}-v2`;
    const result: WorkspaceCommandResult = {
      command_id: `cmd_${Date.now()}`,
      status: 'COMPLETED',
      updated_revision_id: newRev,
      message: `Command ${request.command_type} executed successfully`,
      current_sequence: this.currentSequence,
      payload: request.payload,
    };

    this.idempotencyStore.set(key, result);
    return result;
  }
}

export class ProductionSyncClient {
  private syncState: SyncState = 'OFFLINE';
  private lastSequence: number = 0;
  private dedupeCache = new Set<string>();

  constructor(
    _projectId: string,
    private onEvent: (event: ProductionEventEnvelope) => void,
    private onStateChange: (state: SyncState) => void,
    private onSnapshotResync: () => void
  ) {}

  getSyncState(): SyncState {
    return this.syncState;
  }

  getLastSequence(): number {
    return this.lastSequence;
  }

  private setSyncState(newState: SyncState) {
    if (this.syncState !== newState) {
      this.syncState = newState;
      this.onStateChange(newState);
    }
  }

  handleIncomingEvent(event: ProductionEventEnvelope) {
    const dedupeKey = `${event.event_id}_${event.sequence}`;
    if (this.dedupeCache.has(dedupeKey)) {
      return; // Skip duplicate
    }
    this.dedupeCache.add(dedupeKey);

    // Sequence gap detection
    if (this.lastSequence > 0 && event.sequence > this.lastSequence + 1) {
      this.setSyncState('STALE');
      this.onSnapshotResync();
      return;
    }

    this.lastSequence = event.sequence;
    this.setSyncState('CONNECTED');
    this.onEvent(event);
  }
}
