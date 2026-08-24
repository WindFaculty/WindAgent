/**
 * WindAgentClient — Canonical API Façade for Unified API V3.
 */

export type {
  ProjectResource,
  EpisodeResource,
  CursorPage,
  RuntimeCapabilityProfile,
  StudioSeriesResource,
  StudioSeriesListResponse,
  StudioSeriesCreateResponse,
  StudioSeriesUpdateResponse,
  StudioEpisodeResource,
  StudioEpisodeListResponse,
  StudioEpisodeCreateResponse,
  StudioUpdateEpisodeRequest,
  StudioUpdateEpisodeResponse,
  StudioSelectIdeaRequest,
  StudioSelectIdeaResponse,
  StudioRecordApprovalRequest,
  StudioRecordApprovalResponse,
  StudioDeriveRevisionRequest,
  StudioDeriveRevisionResponse,
  StudioLockScreenplayRequest,
  StudioLockScreenplayResponse,
} from '@windagent/api-contracts';

import type {
  ProjectResource,
  EpisodeResource,
  CursorPage,
  RuntimeCapabilityProfile,
  StudioSeriesListResponse,
  StudioSeriesCreateResponse,
  StudioSeriesUpdateResponse,
  StudioEpisodeListResponse,
  StudioEpisodeCreateResponse,
  StudioUpdateEpisodeRequest,
  StudioUpdateEpisodeResponse,
  StudioSelectIdeaRequest,
  StudioSelectIdeaResponse,
  StudioRecordApprovalRequest,
  StudioRecordApprovalResponse,
  StudioDeriveRevisionRequest,
  StudioDeriveRevisionResponse,
  StudioLockScreenplayRequest,
  StudioLockScreenplayResponse,
  StudioPreflightReport,
  ReadinessResponse,
  AgentDefinitionResource,
  AgentInstanceResource,
  AgentSummaryMetrics,
  AgentActivityItem,
  TaskResource,
  ConversationResource,
  ConversationDetailResource,
  WorkflowDefinitionResource,
  WorkflowStepDefinition,
  WorkflowRunResource,
  AssetResource,
  AssetRevisionResource,
  AssetProvenance,
  CommandReceipt,
  SystemMetrics,
  SystemHealth,
  DashboardSummary,
  WorkersMonitoringResponse,
  ProvidersMonitoringResponse,
  AgentsMonitoringResponse,
  QueuesMonitoringResponse,
  RunsMonitoringResponse,
  ProjectTemplate,
  EpisodeArtifactEnvelope,
  PipelineRun,
  // Phase 9 — Story Production Domain
  CharacterResource,
  CharacterRelationship,
  WorldBibleResource,
  LocationResource,
  FactionResource,
  LoreEntryResource,
  StoryboardResource,
  SceneResource,
  GenerationJobResource,
  ReviewResource,
  ReviewCommentResource,
  ReviewDecisionResource,
  ReviewSubjectType,
  ReviewDecisionKind,
  // Phase 10 — Production Cutover
  ProductionPlanResource,
  ShotResource,
  ProductionJobResource,
  JobSubmissionReceipt,
  DeliveryArtifactResource,
  // P1.6 — Production Package
  ProductionTarget,
  ProductionPreflight,
  ProductionPackageResource,
  FinalizePackageResult,
  // Phase 12 — Models, Providers & Routing
  ModelDefinitionResource,
  ModelFilterParams,
  ProviderResource,
  ProviderEndpointResource,
  ProviderHealthMap,
  ProviderStatus,
  ProviderConnectionTestResult,
  AddProviderRequest,
  ProviderModelRuleResource,
  AssignProviderModelRuleRequest,
  UpdateProviderRequest,
  RotateCredentialRequest,
  CredentialStatusResource,
  DeleteProviderResult,
  SyncModelsResult,
  TestModelRequest,
  ModelProbeReceiptResource,
  RoutingRuleResource,
  RoutingGraphData,
  RoutingMetricsData,
  RouteSimulationRequest,
  RouteDecisionResource,
  RouteLockDetailResource,
  StoryRoleResource,
  RouteReceiptResource,
  // Phase 13 — Platform & Administration Domain
  BrowserSessionResource,
  CreateBrowserSessionRequest,
  BrowserActionResponse,
  FileResource,
  CreateFileRequest,
  MemoryRecordResource,
  CreateMemoryRequest,
  MemorySearchRequest,
  LogRecord,
  LogQueryParams,
  SettingsResponse,
  PatchSettingsRequest,
} from '@windagent/api-contracts';
import { HttpTransport, type TransportOptions } from './transport';

export class ProjectsApi {
  constructor(private transport: HttpTransport) {}

  async list(params?: { search?: string; genre?: string; cursor?: string; limit?: number } | string): Promise<CursorPage<ProjectResource>> {
    if (typeof params === 'string') {
      return this.transport.get<CursorPage<ProjectResource>>('/api/v3/projects', { cursor: params });
    }
    return this.transport.get<CursorPage<ProjectResource>>('/api/v3/projects', params);
  }

  async get(projectId: string): Promise<ProjectResource> {
    return this.transport.get<ProjectResource>(`/api/v3/projects/${encodeURIComponent(projectId)}`);
  }

  async getTemplates(): Promise<ProjectTemplate[]> {
    return this.transport.get<ProjectTemplate[]>('/api/v3/project-templates');
  }

  async create(data: { name: string; description?: string; genre?: string; initial_episode_title?: string }, idempotencyKey: string): Promise<ProjectResource> {
    return this.transport.post<ProjectResource>('/api/v3/projects', data, { idempotencyKey });
  }

  async update(projectId: string, data: { name?: string; description?: string; expected_version: number }, idempotencyKey?: string): Promise<ProjectResource> {
    return this.transport.patch<ProjectResource>(`/api/v3/projects/${encodeURIComponent(projectId)}`, data, { idempotencyKey });
  }
}

export class EpisodesApi {
  constructor(private transport: HttpTransport) {}

  async listAll(params?: { project_id?: string; state?: string; search?: string; limit?: number }): Promise<CursorPage<EpisodeResource>> {
    return this.transport.get<CursorPage<EpisodeResource>>('/api/v3/episodes', params);
  }

  async list(projectId: string): Promise<CursorPage<EpisodeResource>> {
    return this.transport.get<CursorPage<EpisodeResource>>(`/api/v3/projects/${encodeURIComponent(projectId)}/episodes`);
  }

  async get(episodeId: string): Promise<EpisodeResource>;
  async get(projectId: string, episodeId: string): Promise<EpisodeResource>;
  async get(first: string, second?: string): Promise<EpisodeResource> {
    if (second) {
      return this.transport.get<EpisodeResource>(`/api/v3/projects/${encodeURIComponent(first)}/episodes/${encodeURIComponent(second)}`);
    }
    return this.transport.get<EpisodeResource>(`/api/v3/episodes/${encodeURIComponent(first)}`);
  }

  async create(projectId: string, data: { title: string; episode_number?: number }, idempotencyKey: string): Promise<EpisodeResource> {
    return this.transport.post<EpisodeResource>(`/api/v3/projects/${encodeURIComponent(projectId)}/episodes`, data, { idempotencyKey });
  }

  async update(episodeId: string, data: { title?: string; description?: string; expected_version: number }): Promise<EpisodeResource> {
    return this.transport.patch<EpisodeResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}`, data);
  }

  async delete(episodeId: string): Promise<void> {
    return this.transport.delete<void>(`/api/v3/episodes/${encodeURIComponent(episodeId)}`);
  }

  async getArtifacts(episodeId: string): Promise<EpisodeArtifactEnvelope[]> {
    return this.transport.get<EpisodeArtifactEnvelope[]>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/artifacts`);
  }

  async getRuns(episodeId: string): Promise<PipelineRun[]> {
    return this.transport.get<PipelineRun[]>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/runs`);
  }

  async selectIdea(episodeId: string, data: { idea_id: string; expected_version: number }): Promise<EpisodeResource> {
    return this.transport.post<EpisodeResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/select-idea`, data);
  }

  async submitDecision(episodeId: string, data: { decision: 'APPROVED' | 'REVISE' | 'REJECTED'; revision_id: string; feedback?: string; expected_version: number }): Promise<EpisodeResource> {
    return this.transport.post<EpisodeResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/decision`, data);
  }

  async lockScreenplay(episodeId: string, data: { revision_id: string; content_hash: string; expected_version: number }): Promise<EpisodeResource> {
    return this.transport.post<EpisodeResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/lock`, data);
  }

  async cancelRun(episodeId: string): Promise<{ episode_id: string; status: string }> {
    return this.transport.post<{ episode_id: string; status: string }>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/cancel-run`, {});
  }
}


export class StudioApi {
  constructor(private transport: HttpTransport) {}

  async getCapabilities(): Promise<RuntimeCapabilityProfile> {
    return this.transport.get<RuntimeCapabilityProfile>('/api/v3/studio/capabilities');
  }

  async getReadiness(): Promise<ReadinessResponse> {
    return this.transport.get<ReadinessResponse>('/api/v3/studio/readiness');
  }

  // ── P0.7 — canonical Series / Episodes / Runs surfaces ──────────────────

  async listSeries(params?: { cursor?: string; limit?: number }): Promise<StudioSeriesListResponse> {    return this.transport.get<StudioSeriesListResponse>('/api/v3/studio/series', params);
  }

  async createSeries(data: { title: string; description?: string; metadata?: Record<string, unknown> }, idempotencyKey: string): Promise<StudioSeriesCreateResponse> {
    return this.transport.post<StudioSeriesCreateResponse>('/api/v3/studio/series', {
      schema_version: 'studio.command/v1',
      title: data.title,
      description: data.description ?? '',
      metadata: data.metadata ?? {},
    }, { headers: { 'X-Idempotency-Key': idempotencyKey } });
  }

  async updateSeries(seriesId: string, data: { title?: string; description?: string; metadata_patch?: Record<string, unknown> }, idempotencyKey: string): Promise<StudioSeriesUpdateResponse> {
    return this.transport.patch<StudioSeriesUpdateResponse>(
      `/api/v3/studio/series/${encodeURIComponent(seriesId)}`,
      data,
      { headers: { 'X-Idempotency-Key': idempotencyKey } },
    );
  }

  async getSeries(seriesId: string): Promise<Record<string, unknown>> {
    return this.transport.get<Record<string, unknown>>(`/api/v3/studio/series/${encodeURIComponent(seriesId)}`);
  }

  async listEpisodes(seriesId: string): Promise<StudioEpisodeListResponse> {
    return this.transport.get<StudioEpisodeListResponse>(`/api/v3/studio/series/${encodeURIComponent(seriesId)}/episodes`);
  }

  async createEpisode(seriesId: string, data: { series_id: string; title: string; episode_number?: number; metadata?: Record<string, unknown> }, idempotencyKey: string): Promise<StudioEpisodeCreateResponse> {
    return this.transport.post<StudioEpisodeCreateResponse>(`/api/v3/studio/series/${encodeURIComponent(seriesId)}/episodes`, {
      schema_version: 'studio.command/v1',
      series_id: data.series_id,
      title: data.title,
      episode_number: data.episode_number ?? 1,
      metadata: data.metadata ?? {},
    }, { headers: { 'X-Idempotency-Key': idempotencyKey } });
  }

  async getEpisode(episodeId: string): Promise<Record<string, unknown>> {
    return this.transport.get<Record<string, unknown>>(`/api/v3/studio/episodes/${encodeURIComponent(episodeId)}`);
  }

  /** Canonical content-addressed story artifacts (includes content_hash). */
  async listEpisodeArtifacts(episodeId: string): Promise<Array<Record<string, any>>> {
    return this.transport.get<Array<Record<string, any>>>(`/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/artifacts`);
  }

  async preflightStart(episodeId: string): Promise<StudioPreflightReport> {
    return this.transport.get<StudioPreflightReport>(`/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/preflight`);
  }

  /** Start or resume the durable Story run (202 + Location). */
  async startRun(episodeId: string, idempotencyKey: string): Promise<{ run_id: string; episode_id: string; resuming: boolean; run_url: string }> {
    return this.transport.post(`/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/runs`, {}, { headers: { 'X-Idempotency-Key': idempotencyKey } });
  }

  async selectIdea(
    episodeId: string,
    data: StudioSelectIdeaRequest,
    idempotencyKey?: string,
  ): Promise<StudioSelectIdeaResponse> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.transport.post<StudioSelectIdeaResponse>(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/idea-selection`,
      {
        schema_version: 'studio.command/v1',
        episode_id: data.episode_id || episodeId,
        revision_id: data.revision_id,
        candidate_id: data.candidate_id,
        expected_content_hash: data.expected_content_hash,
        expected_optimistic_version: data.expected_optimistic_version,
      },
      { headers: { 'X-Idempotency-Key': key } },
    );
  }

  async recordApproval(
    episodeId: string,
    data: StudioRecordApprovalRequest,
    idempotencyKey?: string,
    actor: string = 'human_user',
  ): Promise<StudioRecordApprovalResponse> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.transport.post<StudioRecordApprovalResponse>(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/approvals`,
      {
        schema_version: 'studio.command/v1',
        episode_id: data.episode_id || episodeId,
        revision_id: data.revision_id,
        checkpoint: data.checkpoint,
        artifact_hash: data.artifact_hash,
        decision: data.decision,
        reason: data.reason || '',
        expected_optimistic_version: data.expected_optimistic_version,
      },
      {
        headers: {
          'X-Idempotency-Key': key,
          'X-WindAgent-Actor': actor,
        },
      },
    );
  }

  async deriveRevision(
    episodeId: string,
    data: StudioDeriveRevisionRequest,
    idempotencyKey?: string,
    actor: string = 'human_user',
  ): Promise<StudioDeriveRevisionResponse> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.transport.post<StudioDeriveRevisionResponse>(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/revisions`,
      {
        schema_version: 'studio.command/v1',
        episode_id: data.episode_id || episodeId,
        series_id: data.series_id,
        parent_revision_id: data.parent_revision_id,
        new_content_hash: data.new_content_hash,
        summary: data.summary || '',
        invalidation_intent: data.invalidation_intent || null,
        expected_optimistic_version: data.expected_optimistic_version,
      },
      {
        headers: {
          'X-Idempotency-Key': key,
          'X-WindAgent-Actor': actor,
        },
      },
    );
  }

  async lockScreenplay(
    episodeId: string,
    data: StudioLockScreenplayRequest,
    idempotencyKey?: string,
  ): Promise<StudioLockScreenplayResponse> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.transport.post<StudioLockScreenplayResponse>(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/screenplay-lock`,
      {
        schema_version: 'studio.command/v1',
        episode_id: data.episode_id || episodeId,
        revision_id: data.revision_id,
        expected_content_hash: data.expected_content_hash,
        expected_optimistic_version: data.expected_optimistic_version,
      },
      { headers: { 'X-Idempotency-Key': key } },
    );
  }

  async updateEpisode(
    episodeId: string,
    data: StudioUpdateEpisodeRequest,
    idempotencyKey?: string,
  ): Promise<StudioUpdateEpisodeResponse> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.transport.patch<StudioUpdateEpisodeResponse>(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}`,
      {
        schema_version: 'studio.command/v1',
        episode_id: episodeId,
        title: data.title,
        metadata_patch: data.metadata_patch || {},
        expected_optimistic_version: data.expected_optimistic_version,
      },
      { headers: { 'X-Idempotency-Key': key } },
    );
  }
}

export class AgentDefinitionsApi {
  constructor(private transport: HttpTransport) {}

  async list(params?: { search?: string; role?: string }): Promise<AgentDefinitionResource[]> {
    return this.transport.get<AgentDefinitionResource[]>('/api/v3/agent-definitions', params);
  }

  async get(definitionId: string): Promise<AgentDefinitionResource> {
    return this.transport.get<AgentDefinitionResource>(`/api/v3/agent-definitions/${encodeURIComponent(definitionId)}`);
  }

  async create(data: {
    name: string;
    slug?: string;
    description?: string;
    role: string;
    model_policy?: Record<string, unknown>;
    tool_policy?: Record<string, unknown>;
    permission_profile?: Record<string, unknown>;
    memory_policy?: Record<string, unknown>;
    default_configuration?: Record<string, unknown>;
  }): Promise<AgentDefinitionResource> {
    return this.transport.post<AgentDefinitionResource>('/api/v3/agent-definitions', data);
  }

  async update(
    definitionId: string,
    data: {
      name?: string;
      slug?: string;
      description?: string;
      role?: string;
      model_policy?: Record<string, unknown>;
      tool_policy?: Record<string, unknown>;
      permission_profile?: Record<string, unknown>;
      memory_policy?: Record<string, unknown>;
      default_configuration?: Record<string, unknown>;
      expected_version: number;
    }
  ): Promise<AgentDefinitionResource> {
    return this.transport.patch<AgentDefinitionResource>(`/api/v3/agent-definitions/${encodeURIComponent(definitionId)}`, data);
  }

  async delete(definitionId: string): Promise<void> {
    return this.transport.delete<void>(`/api/v3/agent-definitions/${encodeURIComponent(definitionId)}`);
  }

  async getActivity(definitionId: string): Promise<AgentActivityItem[]> {
    return this.transport.get<AgentActivityItem[]>(`/api/v3/agent-definitions/${encodeURIComponent(definitionId)}/activity`);
  }

  async getMetrics(): Promise<AgentSummaryMetrics> {
    return this.transport.get<AgentSummaryMetrics>('/api/v3/agents/metrics');
  }
}

export class AgentInstancesApi {
  constructor(private transport: HttpTransport) {}

  async list(params?: { conversation_id?: string; definition_id?: string; status?: string }): Promise<AgentInstanceResource[]> {
    return this.transport.get<AgentInstanceResource[]>('/api/v3/agent-instances', params);
  }

  async get(instanceId: string): Promise<AgentInstanceResource> {
    return this.transport.get<AgentInstanceResource>(`/api/v3/agent-instances/${encodeURIComponent(instanceId)}`);
  }

  async launch(data: {
    definition_id: string;
    conversation_id?: string;
    canonical_model_id?: string;
    runtime_metadata?: Record<string, unknown>;
  }): Promise<AgentInstanceResource> {
    return this.transport.post<AgentInstanceResource>('/api/v3/agent-instances', data);
  }

  async start(instanceId: string): Promise<AgentInstanceResource> {
    return this.transport.post<AgentInstanceResource>(`/api/v3/agent-instances/${encodeURIComponent(instanceId)}/start`, {});
  }

  async stop(instanceId: string): Promise<AgentInstanceResource> {
    return this.transport.post<AgentInstanceResource>(`/api/v3/agent-instances/${encodeURIComponent(instanceId)}/stop`, {});
  }

  async restart(instanceId: string): Promise<AgentInstanceResource> {
    return this.transport.post<AgentInstanceResource>(`/api/v3/agent-instances/${encodeURIComponent(instanceId)}/restart`, {});
  }
}

export class ConversationsApi {
  constructor(private transport: HttpTransport) {}

  async list(): Promise<ConversationResource[]> {
    return this.transport.get<ConversationResource[]>('/api/v3/conversations');
  }

  async get(conversationId: string): Promise<ConversationDetailResource> {
    return this.transport.get<ConversationDetailResource>(`/api/v3/conversations/${encodeURIComponent(conversationId)}`);
  }

  async create(data: { title?: string; objective: string }): Promise<ConversationResource> {
    return this.transport.post<ConversationResource>('/api/v3/conversations', data);
  }

  async getAgents(conversationId: string): Promise<AgentInstanceResource[]> {
    return this.transport.get<AgentInstanceResource[]>(`/api/v3/conversations/${encodeURIComponent(conversationId)}/agents`);
  }

  async getTasks(conversationId: string): Promise<TaskResource[]> {
    return this.transport.get<TaskResource[]>(`/api/v3/conversations/${encodeURIComponent(conversationId)}/tasks`);
  }

  async getEvents(conversationId: string): Promise<Record<string, unknown>[]> {
    return this.transport.get<Record<string, unknown>[]>(`/api/v3/conversations/${encodeURIComponent(conversationId)}/events`);
  }

  async stopAgent(conversationId: string, agentId: string): Promise<AgentInstanceResource> {
    return this.transport.post<AgentInstanceResource>(`/api/v3/conversations/${encodeURIComponent(conversationId)}/agents/${encodeURIComponent(agentId)}/stop`, {});
  }
}

export class TasksApi {
  constructor(private transport: HttpTransport) {}

  async list(params?: { conversation_id?: string; state?: string; assigned_agent_instance_id?: string }): Promise<TaskResource[]> {
    return this.transport.get<TaskResource[]>('/api/v3/tasks', params);
  }

  async get(taskId: string): Promise<TaskResource> {
    return this.transport.get<TaskResource>(`/api/v3/tasks/${encodeURIComponent(taskId)}`);
  }

  async create(data: {
    conversation_id: string;
    objective: string;
    assigned_agent_instance_id?: string;
    parent_task_id?: string;
    dependencies?: string[];
    concurrency_group?: string;
  }): Promise<TaskResource> {
    return this.transport.post<TaskResource>('/api/v3/tasks', data);
  }

  async update(
    taskId: string,
    data: {
      objective?: string;
      state?: string;
      assigned_agent_instance_id?: string;
      dependencies?: string[];
      concurrency_group?: string;
      result?: Record<string, unknown>;
      error?: Record<string, unknown>;
      expected_version: number;
    }
  ): Promise<TaskResource> {
    return this.transport.patch<TaskResource>(`/api/v3/tasks/${encodeURIComponent(taskId)}`, data);
  }

  async cancel(taskId: string): Promise<TaskResource> {
    return this.transport.post<TaskResource>(`/api/v3/tasks/${encodeURIComponent(taskId)}/cancel`, {});
  }

  async retry(taskId: string): Promise<TaskResource> {
    return this.transport.post<TaskResource>(`/api/v3/tasks/${encodeURIComponent(taskId)}/retry`, {});
  }
}

export class WorkflowsApi {
  constructor(private transport: HttpTransport) {}

  async list(params?: { search?: string; type?: string }): Promise<WorkflowDefinitionResource[]> {
    return this.transport.get<WorkflowDefinitionResource[]>('/api/v3/workflows', params);
  }

  async get(workflowId: string): Promise<WorkflowDefinitionResource> {
    return this.transport.get<WorkflowDefinitionResource>(`/api/v3/workflows/${encodeURIComponent(workflowId)}`);
  }

  async create(data: {
    name: string;
    description?: string;
    type?: string;
    trigger?: string;
    owner?: string;
    tags?: string[];
    steps?: WorkflowStepDefinition[];
    acceptance_criteria?: string[];
  }): Promise<WorkflowDefinitionResource> {
    return this.transport.post<WorkflowDefinitionResource>('/api/v3/workflows', data);
  }

  async update(
    workflowId: string,
    data: {
      name?: string;
      description?: string;
      type?: string;
      trigger?: string;
      owner?: string;
      tags?: string[];
      steps?: WorkflowStepDefinition[];
      acceptance_criteria?: string[];
      expected_version: number;
    }
  ): Promise<WorkflowDefinitionResource> {
    return this.transport.patch<WorkflowDefinitionResource>(`/api/v3/workflows/${encodeURIComponent(workflowId)}`, data);
  }

  async listRuns(params?: { workflow_id?: string; status?: string }): Promise<WorkflowRunResource[]> {
    return this.transport.get<WorkflowRunResource[]>('/api/v3/workflow-runs', params);
  }

  async getRun(runId: string): Promise<WorkflowRunResource> {
    return this.transport.get<WorkflowRunResource>(`/api/v3/workflow-runs/${encodeURIComponent(runId)}`);
  }

  async triggerRun(data: {
    workflow_id: string;
    triggered_by?: string;
    parameters?: Record<string, unknown>;
  }): Promise<WorkflowRunResource> {
    return this.transport.post<WorkflowRunResource>('/api/v3/workflow-runs', data);
  }

  async cancelRun(runId: string): Promise<WorkflowRunResource> {
    return this.transport.post<WorkflowRunResource>(`/api/v3/workflow-runs/${encodeURIComponent(runId)}/cancel`, {});
  }

  async retryRun(runId: string): Promise<WorkflowRunResource> {
    return this.transport.post<WorkflowRunResource>(`/api/v3/workflow-runs/${encodeURIComponent(runId)}/retry`, {});
  }

  async pauseRun(runId: string): Promise<WorkflowRunResource> {
    return this.transport.post<WorkflowRunResource>(`/api/v3/workflow-runs/${encodeURIComponent(runId)}/pause`, {});
  }

  async resumeRun(runId: string): Promise<WorkflowRunResource> {
    return this.transport.post<WorkflowRunResource>(`/api/v3/workflow-runs/${encodeURIComponent(runId)}/resume`, {});
  }
}

export class AgentsApi {
  constructor(private transport: HttpTransport) {}

  async listDefinitions(): Promise<CursorPage<AgentDefinitionResource>> {
    return this.transport.get<CursorPage<AgentDefinitionResource>>('/api/v3/agents/definitions');
  }

  async listInstances(): Promise<CursorPage<AgentInstanceResource>> {
    return this.transport.get<CursorPage<AgentInstanceResource>>('/api/v3/agents/instances');
  }

  async executeTask(instanceId: string, data: { task: string }, idempotencyKey: string): Promise<CommandReceipt> {
    return this.transport.post<CommandReceipt>(`/api/v3/agents/instances/${encodeURIComponent(instanceId)}/execute`, data, { idempotencyKey });
  }
}

// ─── Phase 9A: Characters ─────────────────────────────────────────────────

export class CharactersApi {
  constructor(private transport: HttpTransport) {}

  async list(projectId: string, search?: string): Promise<CharacterResource[]> {
    return this.transport.get<CharacterResource[]>(
      `/api/v3/projects/${encodeURIComponent(projectId)}/characters`,
      search ? { search } : undefined,
    );
  }

  async get(characterId: string): Promise<CharacterResource> {
    return this.transport.get<CharacterResource>(`/api/v3/characters/${encodeURIComponent(characterId)}`);
  }

  async create(
    projectId: string,
    data: { name: string; role?: string; biography?: string; dominant_trait?: string; flaw?: string; alignment_score?: number; voice_model_id?: string; voice_style?: string },
    idempotencyKey: string,
  ): Promise<CharacterResource> {
    return this.transport.post<CharacterResource>(
      `/api/v3/projects/${encodeURIComponent(projectId)}/characters`,
      data,
      { idempotencyKey },
    );
  }

  async update(
    characterId: string,
    data: { name?: string; role?: string; biography?: string; dominant_trait?: string; flaw?: string; alignment_score?: number; voice_model_id?: string; voice_style?: string; expected_version: number },
  ): Promise<CharacterResource> {
    return this.transport.patch<CharacterResource>(`/api/v3/characters/${encodeURIComponent(characterId)}`, data);
  }

  async delete(characterId: string): Promise<void> {
    return this.transport.delete<void>(`/api/v3/characters/${encodeURIComponent(characterId)}`);
  }

  async getRelationships(characterId: string): Promise<CharacterRelationship[]> {
    return this.transport.get<CharacterRelationship[]>(`/api/v3/characters/${encodeURIComponent(characterId)}/relationships`);
  }

  async getAssets(characterId: string): Promise<AssetResource[]> {
    return this.transport.get<AssetResource[]>(`/api/v3/characters/${encodeURIComponent(characterId)}/assets`);
  }
}

// ─── Phase 9B: World Bible ────────────────────────────────────────────────

export class WorldApi {
  constructor(private transport: HttpTransport) {}

  async getWorldBible(projectId: string): Promise<WorldBibleResource> {
    return this.transport.get<WorldBibleResource>(`/api/v3/projects/${encodeURIComponent(projectId)}/world`);
  }

  async updateWorldBible(projectId: string, data: { world_name?: string; setting_summary?: string; core_theme?: string; rules?: string[]; timeline_era?: string; expected_version: number }): Promise<WorldBibleResource> {
    return this.transport.patch<WorldBibleResource>(`/api/v3/projects/${encodeURIComponent(projectId)}/world`, data);
  }

  async listLocations(projectId: string): Promise<LocationResource[]> {
    return this.transport.get<LocationResource[]>(`/api/v3/projects/${encodeURIComponent(projectId)}/world/locations`);
  }

  async createLocation(projectId: string, data: { name: string; type?: string; description?: string; atmosphere?: string }): Promise<LocationResource> {
    return this.transport.post<LocationResource>(`/api/v3/projects/${encodeURIComponent(projectId)}/world/locations`, data);
  }

  async listFactions(projectId: string): Promise<FactionResource[]> {
    return this.transport.get<FactionResource[]>(`/api/v3/projects/${encodeURIComponent(projectId)}/world/factions`);
  }

  async createFaction(projectId: string, data: { name: string; ideology?: string; influence_level?: number; description?: string }): Promise<FactionResource> {
    return this.transport.post<FactionResource>(`/api/v3/projects/${encodeURIComponent(projectId)}/world/factions`, data);
  }

  async listLore(projectId: string): Promise<LoreEntryResource[]> {
    return this.transport.get<LoreEntryResource[]>(`/api/v3/projects/${encodeURIComponent(projectId)}/world/lore`);
  }

  async createLore(projectId: string, data: { title: string; category?: string; content?: string }): Promise<LoreEntryResource> {
    return this.transport.post<LoreEntryResource>(`/api/v3/projects/${encodeURIComponent(projectId)}/world/lore`, data);
  }
}

// ─── Phase 9C: Storyboard ─────────────────────────────────────────────────

export class StoryboardApi {
  constructor(private transport: HttpTransport) {}

  async getStoryboard(episodeId: string): Promise<StoryboardResource> {
    return this.transport.get<StoryboardResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/storyboard`);
  }

  async syncFromScreenplay(episodeId: string): Promise<StoryboardResource> {
    return this.transport.post<StoryboardResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/storyboard/actions/sync`, {});
  }

  async listScenes(episodeId: string): Promise<SceneResource[]> {
    return this.transport.get<SceneResource[]>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/storyboard/scenes`);
  }

  async createScene(data: { title: string; script_text?: string; location?: string; character_ids?: string[]; duration_seconds?: number; source_screenplay_revision_id?: string }): Promise<SceneResource> {
    return this.transport.post<SceneResource>('/api/v3/storyboard/scenes', data);
  }

  async updateScene(sceneId: string, data: { title?: string; script_text?: string; location?: string; character_ids?: string[]; expected_version: number }): Promise<SceneResource> {
    return this.transport.patch<SceneResource>(`/api/v3/storyboard/scenes/${encodeURIComponent(sceneId)}`, data);
  }

  /** Triggers concept art generation — returns server-issued generation_id. No fake timers. */
  async triggerGeneration(sceneId: string, data?: { style_prompt?: string; reference_character_ids?: string[] }): Promise<GenerationJobResource> {
    return this.transport.post<GenerationJobResource>(`/api/v3/storyboard/scenes/${encodeURIComponent(sceneId)}/generations`, data ?? {});
  }

  async getGenerationJob(sceneId: string, generationId: string): Promise<GenerationJobResource> {
    return this.transport.get<GenerationJobResource>(`/api/v3/storyboard/scenes/${encodeURIComponent(sceneId)}/generations/${encodeURIComponent(generationId)}`);
  }
}

// ─── Phase 9D: Reviews ────────────────────────────────────────────────────

export class ReviewsApi {
  constructor(private transport: HttpTransport) {}

  async list(params?: { subject_type?: ReviewSubjectType; episode_id?: string; project_id?: string; status?: string }): Promise<ReviewResource[]> {
    return this.transport.get<ReviewResource[]>('/api/v3/reviews', params);
  }

  async create(data: { subject_type: ReviewSubjectType; subject_id: string; episode_id?: string; project_id?: string }): Promise<ReviewResource> {
    return this.transport.post<ReviewResource>('/api/v3/reviews', data);
  }

  async get(reviewId: string): Promise<ReviewResource> {
    return this.transport.get<ReviewResource>(`/api/v3/reviews/${encodeURIComponent(reviewId)}`);
  }

  async listComments(reviewId: string): Promise<ReviewCommentResource[]> {
    return this.transport.get<ReviewCommentResource[]>(`/api/v3/reviews/${encodeURIComponent(reviewId)}/comments`);
  }

  async addComment(reviewId: string, data: { author: string; role?: string; text: string }): Promise<ReviewCommentResource> {
    return this.transport.post<ReviewCommentResource>(`/api/v3/reviews/${encodeURIComponent(reviewId)}/comments`, data);
  }

  async submitDecision(
    reviewId: string,
    data: { decision: ReviewDecisionKind; revision_id: string; expected_version: number; reason?: string; decided_by: string },
  ): Promise<ReviewDecisionResource> {
    return this.transport.post<ReviewDecisionResource>(`/api/v3/reviews/${encodeURIComponent(reviewId)}/decision`, data);
  }
}

// ─── Phase 9E: Assets (canonical V3) ─────────────────────────────────────

export class AssetsApi {
  constructor(private transport: HttpTransport) {}

  async list(params?: { episode_id?: string; project_id?: string; scene_id?: string; type?: string; status?: string }): Promise<AssetResource[]> {
    return this.transport.get<AssetResource[]>('/api/v3/assets', params);
  }

  async get(assetId: string): Promise<AssetResource> {
    return this.transport.get<AssetResource>(`/api/v3/assets/${encodeURIComponent(assetId)}`);
  }

  async create(data: { name: string; type?: string; episode_id?: string; project_id?: string; scene_id?: string; character_id?: string; source?: string; generator?: string; model?: string; prompt?: string; job_id?: string; parent_revision_id?: string; media_url?: string }): Promise<AssetResource> {
    return this.transport.post<AssetResource>('/api/v3/assets', data);
  }

  async listRevisions(assetId: string): Promise<AssetRevisionResource[]> {
    return this.transport.get<AssetRevisionResource[]>(`/api/v3/assets/${encodeURIComponent(assetId)}/revisions`);
  }

  async getProvenance(assetId: string): Promise<AssetProvenance> {
    return this.transport.get<AssetProvenance>(`/api/v3/assets/${encodeURIComponent(assetId)}/provenance`);
  }

  async getDependencies(assetId: string): Promise<string[]> {
    return this.transport.get<string[]>(`/api/v3/assets/${encodeURIComponent(assetId)}/dependencies`);
  }

  async approve(assetId: string, data: { revision_id: string; reason?: string; approved_by: string }): Promise<AssetResource> {
    return this.transport.post<AssetResource>(`/api/v3/assets/${encodeURIComponent(assetId)}/actions/approve`, data);
  }

  async reject(assetId: string, data: { revision_id: string; reason?: string; rejected_by: string }): Promise<AssetResource> {
    return this.transport.post<AssetResource>(`/api/v3/assets/${encodeURIComponent(assetId)}/actions/reject`, data);
  }
}

export class DashboardApi {
  constructor(private transport: HttpTransport) {}

  async getSummary(): Promise<DashboardSummary> {
    return this.transport.get<DashboardSummary>('/api/v3/dashboard/summary');
  }
}

export class MonitoringApi {
  constructor(private transport: HttpTransport) {}

  async getWorkers(): Promise<WorkersMonitoringResponse> {
    return this.transport.get<WorkersMonitoringResponse>('/api/v3/monitoring/workers');
  }

  async getProviders(): Promise<ProvidersMonitoringResponse> {
    return this.transport.get<ProvidersMonitoringResponse>('/api/v3/monitoring/providers');
  }

  async getAgents(): Promise<AgentsMonitoringResponse> {
    return this.transport.get<AgentsMonitoringResponse>('/api/v3/monitoring/agents');
  }

  async getQueues(): Promise<QueuesMonitoringResponse> {
    return this.transport.get<QueuesMonitoringResponse>('/api/v3/monitoring/queues');
  }

  async getRuns(): Promise<RunsMonitoringResponse> {
    return this.transport.get<RunsMonitoringResponse>('/api/v3/monitoring/runs');
  }
}

export class SystemApi {
  constructor(private transport: HttpTransport) {}

  async getHealth(): Promise<{ status: string }> {
    return this.transport.get<{ status: string }>('/health');
  }

  async getV3Health(): Promise<SystemHealth> {
    return this.transport.get<SystemHealth>('/api/v3/system/health');
  }

  async getMetrics(): Promise<SystemMetrics> {
    return this.transport.get<SystemMetrics>('/api/v3/system/metrics');
  }

  async getArchitecture(): Promise<Record<string, unknown>> {
    return this.transport.get<Record<string, unknown>>('/internal/architecture');
  }
}

// ─── Phase 10: Production ──────────────────────────────────────────────────

export class ProductionApi {
  constructor(private transport: HttpTransport) {}

  async getPlan(episodeId: string): Promise<ProductionPlanResource> {
    return this.transport.get<ProductionPlanResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production`);
  }

  async createPlan(episodeId: string, data: { screenplay_revision_id: string; storyboard_revision_id: string; character_references?: string[]; asset_references?: string[] }): Promise<ProductionPlanResource> {
    return this.transport.post<ProductionPlanResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/plan`, data);
  }

  async listShots(episodeId: string): Promise<ShotResource[]> {
    return this.transport.get<ShotResource[]>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/shots`);
  }

  async createShot(episodeId: string, data: { scene_id?: string; shot_number?: number; camera_movement?: string; focal_length?: string; duration_seconds?: number }): Promise<ShotResource> {
    return this.transport.post<ShotResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/shots`, data);
  }

  async getShot(shotId: string): Promise<ShotResource> {
    return this.transport.get<ShotResource>(`/api/v3/shots/${encodeURIComponent(shotId)}`);
  }

  async updateShot(shotId: string, data: { camera_movement?: string; focal_length?: string; duration_seconds?: number; status?: string; audio_asset_id?: string; animation_asset_id?: string; render_asset_id?: string; expected_version: number }): Promise<ShotResource> {
    return this.transport.patch<ShotResource>(`/api/v3/shots/${encodeURIComponent(shotId)}`, data);
  }

  async submitAudioJob(episodeId: string, data?: { shot_id?: string; prompt_override?: string; correlation_id?: string }): Promise<JobSubmissionReceipt> {
    return this.transport.post<JobSubmissionReceipt>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/audio/submit`, data ?? {});
  }

  async cancelAudioJob(episodeId: string, jobId: string, reason?: string): Promise<ProductionJobResource> {
    return this.transport.post<ProductionJobResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/audio/cancel`, { job_id: jobId, reason });
  }

  async retryAudioJob(episodeId: string, jobId: string): Promise<JobSubmissionReceipt> {
    return this.transport.post<JobSubmissionReceipt>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/audio/retry`, { job_id: jobId });
  }

  async submitAnimationJob(episodeId: string, data?: { shot_id?: string; prompt_override?: string; correlation_id?: string }): Promise<JobSubmissionReceipt> {
    return this.transport.post<JobSubmissionReceipt>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/animation/submit`, data ?? {});
  }

  async cancelAnimationJob(episodeId: string, jobId: string, reason?: string): Promise<ProductionJobResource> {
    return this.transport.post<ProductionJobResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/animation/cancel`, { job_id: jobId, reason });
  }

  async retryAnimationJob(episodeId: string, jobId: string): Promise<JobSubmissionReceipt> {
    return this.transport.post<JobSubmissionReceipt>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/animation/retry`, { job_id: jobId });
  }

  async submitRenderJob(episodeId: string, data?: { shot_id?: string; prompt_override?: string; correlation_id?: string }): Promise<JobSubmissionReceipt> {
    return this.transport.post<JobSubmissionReceipt>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/render/submit`, data ?? {});
  }

  async cancelRenderJob(episodeId: string, jobId: string, reason?: string): Promise<ProductionJobResource> {
    return this.transport.post<ProductionJobResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/render/cancel`, { job_id: jobId, reason });
  }

  async retryRenderJob(episodeId: string, jobId: string): Promise<JobSubmissionReceipt> {
    return this.transport.post<JobSubmissionReceipt>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/render/retry`, { job_id: jobId });
  }

  async submitVideoJob(episodeId: string, data?: { prompt_override?: string; correlation_id?: string }): Promise<JobSubmissionReceipt> {
    return this.transport.post<JobSubmissionReceipt>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/video/submit`, data ?? {});
  }

  async cancelVideoJob(episodeId: string, jobId: string, reason?: string): Promise<ProductionJobResource> {
    return this.transport.post<ProductionJobResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/video/cancel`, { job_id: jobId, reason });
  }

  async retryVideoJob(episodeId: string, jobId: string): Promise<JobSubmissionReceipt> {
    return this.transport.post<JobSubmissionReceipt>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/video/retry`, { job_id: jobId });
  }

  async listJobs(episodeId: string, stage?: string): Promise<ProductionJobResource[]> {
    return this.transport.get<ProductionJobResource[]>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/jobs`, stage ? { stage } : undefined);
  }

  async getJob(jobId: string): Promise<ProductionJobResource> {
    return this.transport.get<ProductionJobResource>(`/api/v3/production/jobs/${encodeURIComponent(jobId)}`);
  }

  async getDelivery(episodeId: string): Promise<DeliveryArtifactResource> {
    return this.transport.get<DeliveryArtifactResource>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/delivery`);
  }

  // ── P1.6 — Production Package (readiness + immutable handoff) ────────────

  async preflightPackage(episodeId: string): Promise<ProductionPreflight> {
    return this.transport.get<ProductionPreflight>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/package/preflight`);
  }

  async finalizePackage(
    episodeId: string,
    data: { production_target: ProductionTarget }
  ): Promise<FinalizePackageResult> {
    return this.transport.post<FinalizePackageResult>(
      `/api/v3/episodes/${encodeURIComponent(episodeId)}/production/package/actions/finalize`,
      data
    );
  }

  async listPackages(episodeId: string): Promise<ProductionPackageResource[]> {
    return this.transport.get<ProductionPackageResource[]>(`/api/v3/episodes/${encodeURIComponent(episodeId)}/production/packages`);
  }

  async getPackage(packageId: string): Promise<ProductionPackageResource> {
    return this.transport.get<ProductionPackageResource>(`/api/v3/production/packages/${encodeURIComponent(packageId)}`);
  }
}

// ─── Phase 12: Models, Providers & Routing ──────────────────────────────────

export class ModelsApi {
  constructor(private transport: HttpTransport) {}

  async list(params?: ModelFilterParams): Promise<ModelDefinitionResource[]> {
    return this.transport.get<ModelDefinitionResource[]>('/api/v3/models', { ...params });
  }

  async get(id: string): Promise<ModelDefinitionResource> {
    return this.transport.get<ModelDefinitionResource>(`/api/v3/models/${encodeURIComponent(id)}`);
  }
}

export class ProvidersApi {
  constructor(private transport: HttpTransport) {}

  async list(): Promise<ProviderResource[]> {
    return this.transport.get<ProviderResource[]>('/api/v3/providers');
  }

  async create(request: AddProviderRequest): Promise<ProviderResource> {
    return this.transport.post<ProviderResource>('/api/v3/providers', request);
  }

  async get(id: string): Promise<ProviderResource> {
    return this.transport.get<ProviderResource>(`/api/v3/providers/${encodeURIComponent(id)}`);
  }

  async getModels(id: string): Promise<ModelDefinitionResource[]> {
    return this.transport.get<ModelDefinitionResource[]>(`/api/v3/providers/${encodeURIComponent(id)}/models`);
  }

  async getEndpoints(id: string): Promise<ProviderEndpointResource[]> {
    return this.transport.get<ProviderEndpointResource[]>(`/api/v3/providers/${encodeURIComponent(id)}/endpoints`);
  }

  async getHealth(): Promise<ProviderHealthMap> {
    return this.transport.get<ProviderHealthMap>('/api/v3/providers/health');
  }

  async getProviderHealth(id: string): Promise<ProviderStatus> {
    return this.transport.get<ProviderStatus>(`/api/v3/providers/${encodeURIComponent(id)}/health`);
  }

  async testConnection(id: string, endpointId?: string): Promise<ProviderConnectionTestResult> {
    return this.transport.post<ProviderConnectionTestResult>(`/api/v3/providers/${encodeURIComponent(id)}/test-connection`, { endpoint_id: endpointId });
  }

  async listModelRules(): Promise<ProviderModelRuleResource[]> {
    return this.transport.get<ProviderModelRuleResource[]>('/api/v3/providers/rules');
  }

  async assignModelRule(request: AssignProviderModelRuleRequest): Promise<ProviderModelRuleResource> {
    return this.transport.post<ProviderModelRuleResource>('/api/v3/providers/rules', request);
  }

  /** P0.1 — edit provider identity / endpoint / enabled state (never secrets). */
  async update(id: string, request: UpdateProviderRequest): Promise<ProviderResource> {
    return this.transport.patch<ProviderResource>(`/api/v3/providers/${encodeURIComponent(id)}`, request);
  }

  /** P0.1 — delete; pass allowDisablingRules only as an explicit user decision. */
  async remove(id: string, allowDisablingRules?: boolean): Promise<DeleteProviderResult> {
    return this.transport.delete<DeleteProviderResult>(
      `/api/v3/providers/${encodeURIComponent(id)}`,
      allowDisablingRules ? { query: { allow_disabling_rules: true } } : undefined,
    );
  }

  /** P0.1 — rotate (or first-configure) the credential; raw key never returned. */
  async rotateCredential(id: string, request: RotateCredentialRequest): Promise<CredentialStatusResource> {
    return this.transport.put<CredentialStatusResource>(
      `/api/v3/providers/${encodeURIComponent(id)}/credential`,
      request,
    );
  }

  /** P0.1 — remove the credential; endpoints become unconfigured. */
  async removeCredential(id: string): Promise<CredentialStatusResource> {
    return this.transport.delete<CredentialStatusResource>(
      `/api/v3/providers/${encodeURIComponent(id)}/credential`,
    );
  }

  /** P0.2.1 — explicit model catalog sync (independent from Test Connection). */
  async syncModels(id: string, endpointId?: string): Promise<SyncModelsResult> {
    return this.transport.post<SyncModelsResult>(
      `/api/v3/providers/${encodeURIComponent(id)}/sync-models`,
      { endpoint_id: endpointId },
    );
  }

  /** P0.2.5 — verify one bound model with a tiny real inference. */
  async testModel(id: string, request: TestModelRequest): Promise<ModelProbeReceiptResource> {
    return this.transport.post<ModelProbeReceiptResource>(
      `/api/v3/providers/${encodeURIComponent(id)}/models/test`,
      request,
    );
  }
}

export class RoutingApi {
  constructor(private transport: HttpTransport) {}

  async listRules(): Promise<RoutingRuleResource[]> {
    return this.transport.get<RoutingRuleResource[]>('/api/v3/routing/rules');
  }

  async getRule(id: string): Promise<RoutingRuleResource> {
    return this.transport.get<RoutingRuleResource>(`/api/v3/routing/rules/${encodeURIComponent(id)}`);
  }

  async createRule(rule: Partial<RoutingRuleResource>): Promise<RoutingRuleResource> {
    return this.transport.post<RoutingRuleResource>('/api/v3/routing/rules', rule);
  }

  async updateRule(id: string, updates: Partial<RoutingRuleResource> & { expected_version?: number }): Promise<RoutingRuleResource> {
    return this.transport.patch<RoutingRuleResource>(`/api/v3/routing/rules/${encodeURIComponent(id)}`, updates);
  }

  async deleteRule(id: string): Promise<{ deleted: boolean; id: string }> {
    return this.transport.delete<{ deleted: boolean; id: string }>(`/api/v3/routing/rules/${encodeURIComponent(id)}`);
  }

  async getGraph(): Promise<RoutingGraphData> {
    return this.transport.get<RoutingGraphData>('/api/v3/routing/graph');
  }

  async getMetrics(): Promise<RoutingMetricsData> {
    return this.transport.get<RoutingMetricsData>('/api/v3/routing/metrics');
  }

  async simulate(request: RouteSimulationRequest): Promise<RouteDecisionResource> {
    return this.transport.post<RouteDecisionResource>('/api/v3/routing/simulations', request);
  }

  async getLock(lockId: string): Promise<RouteLockDetailResource> {
    return this.transport.get<RouteLockDetailResource>(`/api/v3/routing/locks/${encodeURIComponent(lockId)}`);
  }

  /** P0.3.1 — canonical story model-routing roles (server authority). */
  async listStoryRoles(): Promise<StoryRoleResource[]> {
    return this.transport.get<StoryRoleResource[]>('/api/v3/routing/roles');
  }

  /** P0.3.6 — durable per-task route receipts. */
  async listReceipts(params?: { task_id?: string; role?: string; limit?: number }): Promise<RouteReceiptResource[]> {
    return this.transport.get<RouteReceiptResource[]>('/api/v3/routing/receipts', params);
  }
}

// ─── Phase 13: Platform & Administration Domain ────────────────────────────

export class BrowserApi {
  constructor(private transport: HttpTransport) {}

  async listSessions(): Promise<BrowserSessionResource[]> {
    return this.transport.get<BrowserSessionResource[]>('/api/v3/browser/sessions');
  }

  async createSession(body: CreateBrowserSessionRequest = {}): Promise<BrowserSessionResource> {
    return this.transport.post<BrowserSessionResource>('/api/v3/browser/sessions', body);
  }

  async getSession(sessionId: string): Promise<BrowserSessionResource> {
    return this.transport.get<BrowserSessionResource>(`/api/v3/browser/sessions/${encodeURIComponent(sessionId)}`);
  }

  async navigate(sessionId: string, url: string): Promise<BrowserActionResponse> {
    return this.transport.post<BrowserActionResponse>(
      `/api/v3/browser/sessions/${encodeURIComponent(sessionId)}/navigate`,
      { url }
    );
  }

  async click(sessionId: string, x: number, y: number): Promise<BrowserActionResponse> {
    return this.transport.post<BrowserActionResponse>(
      `/api/v3/browser/sessions/${encodeURIComponent(sessionId)}/click`,
      { x, y }
    );
  }

  async typeText(sessionId: string, selector: string, text: string): Promise<BrowserActionResponse> {
    return this.transport.post<BrowserActionResponse>(
      `/api/v3/browser/sessions/${encodeURIComponent(sessionId)}/type`,
      { selector, text }
    );
  }

  async scroll(sessionId: string, direction: 'up' | 'down' = 'down', pixels = 800): Promise<BrowserActionResponse> {
    return this.transport.post<BrowserActionResponse>(
      `/api/v3/browser/sessions/${encodeURIComponent(sessionId)}/scroll`,
      { direction, pixels }
    );
  }

  async extract(sessionId: string): Promise<BrowserActionResponse> {
    return this.transport.get<BrowserActionResponse>(
      `/api/v3/browser/sessions/${encodeURIComponent(sessionId)}/extract`
    );
  }

  screenshotUrl(sessionId: string): string {
    return `/api/v3/browser/sessions/${encodeURIComponent(sessionId)}/screenshot`;
  }

  async close(sessionId: string): Promise<void> {
    await this.transport.delete<void>(`/api/v3/browser/sessions/${encodeURIComponent(sessionId)}`);
  }
}

export class FilesApi {
  constructor(private transport: HttpTransport) {}

  async list(): Promise<FileResource[]> {
    return this.transport.get<FileResource[]>('/api/v3/files');
  }

  async create(body: CreateFileRequest): Promise<FileResource> {
    return this.transport.post<FileResource>('/api/v3/files', body);
  }

  async get(fileId: string): Promise<FileResource> {
    return this.transport.get<FileResource>(`/api/v3/files/${encodeURIComponent(fileId)}`);
  }

  downloadUrl(fileId: string): string {
    return `/api/v3/files/${encodeURIComponent(fileId)}/download`;
  }

  async remove(fileId: string): Promise<void> {
    await this.transport.delete<void>(`/api/v3/files/${encodeURIComponent(fileId)}`);
  }
}

export class MemoryApi {
  constructor(private transport: HttpTransport) {}

  async list(params?: { scope?: string; owner?: string; memory_type?: string; limit?: number }): Promise<MemoryRecordResource[]> {
    return this.transport.get<MemoryRecordResource[]>('/api/v3/memory', params);
  }

  async get(memoryId: string): Promise<MemoryRecordResource> {
    return this.transport.get<MemoryRecordResource>(`/api/v3/memory/${encodeURIComponent(memoryId)}`);
  }

  async create(body: CreateMemoryRequest): Promise<MemoryRecordResource> {
    return this.transport.post<MemoryRecordResource>('/api/v3/memory', body);
  }

  async search(body: MemorySearchRequest): Promise<MemoryRecordResource[]> {
    return this.transport.post<MemoryRecordResource[]>('/api/v3/memory/search', body);
  }
}

export class LogsApi {
  constructor(private transport: HttpTransport) {}

  async list(params?: LogQueryParams): Promise<LogRecord[]> {
    return this.transport.get<LogRecord[]>('/api/v3/logs', params as Record<string, unknown> | undefined);
  }

  async sources(): Promise<string[]> {
    return this.transport.get<string[]>('/api/v3/logs/sources');
  }
}

export class SettingsApi {
  constructor(private transport: HttpTransport) {}

  async get(): Promise<SettingsResponse> {
    return this.transport.get<SettingsResponse>('/api/v3/settings');
  }

  async getSchema(): Promise<SettingsResponse> {
    return this.transport.get<SettingsResponse>('/api/v3/settings/schema');
  }

  async patch(values: Record<string, unknown>): Promise<SettingsResponse> {
    const body: PatchSettingsRequest = { values };
    return this.transport.patch<SettingsResponse>('/api/v3/settings', body);
  }
}

// ─── Live Record — Recording Preparation / Plans / Takes / Sessions ─────────

export class LiveRecordApi {
  constructor(private transport: HttpTransport) {}

  // ── Preparations (Episode workspace → DRAFT plan) ─────────────────────────

  async prepare(body: {
    episode_id: string;
    episode_revision_id: string;
    source_workspace_hash?: string;
    recording_profile?: Record<string, unknown> | null;
    scenes: Array<Record<string, unknown>>;
    plan_id?: string | null;
  }, idempotencyKey: string): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(
      '/api/v3/live-record/preparations',
      body,
      { headers: { 'X-Idempotency-Key': idempotencyKey } },
    );
  }

  // ── Plans ──────────────────────────────────────────────────────────────────

  async listPlans(params?: { episode_id?: string; status?: string; limit?: number }): Promise<Record<string, unknown>> {
    return this.transport.get<Record<string, unknown>>('/api/v3/live-record/plans', params);
  }

  async getPlan(planId: string): Promise<Record<string, unknown>> {
    return this.transport.get<Record<string, unknown>>(`/api/v3/live-record/plans/${encodeURIComponent(planId)}`);
  }

  async updatePlanContent(planId: string, data: { expected_version: number } & Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.transport.patch<Record<string, unknown>>(`/api/v3/live-record/plans/${encodeURIComponent(planId)}/content`, data);
  }

  async transitionPlan(planId: string, action: 'prepare' | 'validate' | 'freeze' | 'mark-stale' | 'mark-invalid' | 'staleness-check'): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(`/api/v3/live-record/plans/${encodeURIComponent(planId)}/${action}`, {});
  }

  // ── Takes ─────────────────────────────────────────────────────────────────

  async createTake(planId: string, body: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(`/api/v3/live-record/plans/${encodeURIComponent(planId)}/takes`, body);
  }

  async listTakes(planId: string): Promise<Record<string, unknown>> {
    return this.transport.get<Record<string, unknown>>(`/api/v3/live-record/plans/${encodeURIComponent(planId)}/takes`);
  }

  async getTake(takeId: string): Promise<Record<string, unknown>> {
    return this.transport.get<Record<string, unknown>>(`/api/v3/live-record/takes/${encodeURIComponent(takeId)}`);
  }

  async listTakeEvents(takeId: string, params?: { limit?: number; cursor?: string }): Promise<Record<string, unknown>> {
    return this.transport.get<Record<string, unknown>>(`/api/v3/live-record/takes/${encodeURIComponent(takeId)}/events`, params);
  }

  async appendTakeEvent(takeId: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(`/api/v3/live-record/takes/${encodeURIComponent(takeId)}/events`, body);
  }

  // ── Segments (engine → host → DB lineage, LR_P8) ──────────────────────────

  async recordTakeSegment(takeId: string, body: {
    segment_id?: string;
    segment_index: number;
    file_token?: string;
    started_at?: string | null;
    ended_at?: string | null;
    duration_sec?: number | null;
    is_playable?: boolean;
    manifest?: Record<string, unknown>;
  }): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(
      `/api/v3/live-record/takes/${encodeURIComponent(takeId)}/segments`,
      body,
    );
  }

  async listTakeSegments(takeId: string): Promise<Record<string, unknown>> {
    return this.transport.get<Record<string, unknown>>(`/api/v3/live-record/takes/${encodeURIComponent(takeId)}/segments`);
  }

  // ── Director session bootstrap (ephemeral token, POST-only) ───────────────

  async bootstrapSession(body: {
    episode_id: string;
    execution_plan_id: string;
    current_episode_revision_id?: string | null;
  }, idempotencyKey: string): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(
      '/api/v3/live-record/sessions/bootstrap',
      body,
      { headers: { 'X-Idempotency-Key': idempotencyKey } },
    );
  }

  async getSession(sessionId: string): Promise<Record<string, unknown>> {
    return this.transport.get<Record<string, unknown>>(`/api/v3/live-record/sessions/${encodeURIComponent(sessionId)}`);
  }

  /** Section 24/§35: re-mint the ephemeral token for a reconnecting desktop. */
  async refreshSessionToken(sessionId: string, idempotencyKey: string): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(
      `/api/v3/live-record/sessions/${encodeURIComponent(sessionId)}/token-refresh`,
      {},
      { headers: { 'X-Idempotency-Key': idempotencyKey } },
    );
  }

  // ── Privacy scan (Section 23/33 preflight guard) ─────────────────────────

  async runPrivacyScan(planId: string): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(
      `/api/v3/live-record/plans/${encodeURIComponent(planId)}/privacy-scan`,
      {},
    );
  }

  // ── Prepared actions (dispatch tickets + result verification) ─────────────

  async prepareAction(planId: string, actionId: string): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(
      `/api/v3/live-record/plans/${encodeURIComponent(planId)}/actions/${encodeURIComponent(actionId)}/prepare`,
      {},
    );
  }

  async executeActionCommand(planId: string, actionId: string, body: { cwd?: string; timeout_seconds?: number }, idempotencyKey: string): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(
      `/api/v3/live-record/plans/${encodeURIComponent(planId)}/actions/${encodeURIComponent(actionId)}/execute`,
      body,
      { headers: { 'X-Idempotency-Key': idempotencyKey } },
    );
  }

  async reportActionResult(planId: string, body: {
    take_id: string;
    action_id: string;
    status: 'SUCCESS' | 'FAILURE';
    execution_id: string;
    t: number;
    detail?: string;
    before_hash_observed?: string | null;
    after_hash_observed?: string | null;
    observed?: Record<string, unknown>;
    scene_id?: string | null;
    cue_id?: string | null;
  }, idempotencyKey: string): Promise<Record<string, unknown>> {
    return this.transport.post<Record<string, unknown>>(
      `/api/v3/live-record/plans/${encodeURIComponent(planId)}/actions/result`,
      body,
      { headers: { 'X-Idempotency-Key': idempotencyKey } },
    );
  }
}

export class WindAgentClient {
  readonly transport: HttpTransport;
  readonly projects: ProjectsApi;
  readonly episodes: EpisodesApi;
  readonly studio: StudioApi;
  readonly agents: AgentsApi;
  readonly agentDefinitions: AgentDefinitionsApi;
  readonly agentInstances: AgentInstancesApi;
  readonly conversations: ConversationsApi;
  readonly tasks: TasksApi;
  readonly workflows: WorkflowsApi;
  readonly assets: AssetsApi;
  readonly dashboard: DashboardApi;
  readonly monitoring: MonitoringApi;
  readonly system: SystemApi;
  // Phase 9 — Story Production Domain
  readonly characters: CharactersApi;
  readonly world: WorldApi;
  readonly storyboard: StoryboardApi;
  readonly reviews: ReviewsApi;
  // Phase 10 — Production Cutover Domain
  readonly production: ProductionApi;
  // Phase 12 — Models, Providers & Routing Infrastructure Domain
  readonly models: ModelsApi;
  readonly providers: ProvidersApi;
  readonly routing: RoutingApi;
  // Phase 13 — Platform & Administration Domain
  readonly browser: BrowserApi;
  readonly files: FilesApi;
  readonly memory: MemoryApi;
  readonly logs: LogsApi;
  readonly settings: SettingsApi;
  // Live Record — recording preparation & director sessions
  readonly liveRecord: LiveRecordApi;

  constructor(options: TransportOptions) {
    this.transport = new HttpTransport(options);
    this.projects = new ProjectsApi(this.transport);
    this.episodes = new EpisodesApi(this.transport);
    this.studio = new StudioApi(this.transport);
    this.agents = new AgentsApi(this.transport);
    this.agentDefinitions = new AgentDefinitionsApi(this.transport);
    this.agentInstances = new AgentInstancesApi(this.transport);
    this.conversations = new ConversationsApi(this.transport);
    this.tasks = new TasksApi(this.transport);
    this.workflows = new WorkflowsApi(this.transport);
    this.assets = new AssetsApi(this.transport);
    this.dashboard = new DashboardApi(this.transport);
    this.monitoring = new MonitoringApi(this.transport);
    this.system = new SystemApi(this.transport);
    // Phase 9
    this.characters = new CharactersApi(this.transport);
    this.world = new WorldApi(this.transport);
    this.storyboard = new StoryboardApi(this.transport);
    this.reviews = new ReviewsApi(this.transport);
    // Phase 10
    this.production = new ProductionApi(this.transport);
    // Phase 12
    this.models = new ModelsApi(this.transport);
    this.providers = new ProvidersApi(this.transport);
    this.routing = new RoutingApi(this.transport);
    // Phase 13
    this.browser = new BrowserApi(this.transport);
    this.files = new FilesApi(this.transport);
    this.memory = new MemoryApi(this.transport);
    this.logs = new LogsApi(this.transport);
    this.settings = new SettingsApi(this.transport);
    this.liveRecord = new LiveRecordApi(this.transport);
  }
}

export function createApiClient(options: TransportOptions): WindAgentClient {
  return new WindAgentClient(options);
}
