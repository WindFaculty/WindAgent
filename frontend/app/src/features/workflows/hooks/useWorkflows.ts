/**
 * Phase 11 — Workflows Feature Hooks.
 * Provides query/mutation hooks for Workflow Definitions, Runs, Step Runs,
 * and Lifecycle Controls (Trigger, Pause, Resume, Cancel, Retry).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type {
  WorkflowDefinitionResource,
  WorkflowStepDefinition,
  WorkflowRunResource,
} from '@windagent/api-contracts';

export const workflowKeys = {
  all: ['workflows'] as const,
  definitions: (params?: { search?: string; type?: string }) => [...workflowKeys.all, 'definitions', params ?? {}] as const,
  definition: (id: string) => [...workflowKeys.all, 'definition', id] as const,
  runs: (params?: { workflow_id?: string; status?: string }) => [...workflowKeys.all, 'runs', params ?? {}] as const,
  run: (runId: string) => [...workflowKeys.all, 'run', runId] as const,
};

export function useWorkflowDefinitions(params?: { search?: string; type?: string }) {
  const client = useApiClient();
  return useQuery<WorkflowDefinitionResource[]>({
    queryKey: workflowKeys.definitions(params),
    queryFn: () => client.workflows.list(params),
  });
}

export function useWorkflowDefinition(workflowId: string) {
  const client = useApiClient();
  return useQuery<WorkflowDefinitionResource>({
    queryKey: workflowKeys.definition(workflowId),
    queryFn: () => client.workflows.get(workflowId),
    enabled: Boolean(workflowId),
  });
}

export function useCreateWorkflow() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      description?: string;
      type?: string;
      trigger?: string;
      owner?: string;
      tags?: string[];
      steps?: WorkflowStepDefinition[];
      acceptance_criteria?: string[];
    }) => client.workflows.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.all });
    },
  });
}

export function useUpdateWorkflow() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      workflowId: string;
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
      };
    }) => client.workflows.update(args.workflowId, args.data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.definition(variables.workflowId) });
      queryClient.invalidateQueries({ queryKey: workflowKeys.all });
    },
  });
}

export function useWorkflowRuns(params?: { workflow_id?: string; status?: string }) {
  const client = useApiClient();
  return useQuery<WorkflowRunResource[]>({
    queryKey: workflowKeys.runs(params),
    queryFn: () => client.workflows.listRuns(params),
  });
}

export function useWorkflowRun(runId: string) {
  const client = useApiClient();
  return useQuery<WorkflowRunResource>({
    queryKey: workflowKeys.run(runId),
    queryFn: () => client.workflows.getRun(runId),
    enabled: Boolean(runId),
  });
}

export function useTriggerWorkflowRun() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { workflow_id: string; triggered_by?: string; parameters?: Record<string, unknown> }) =>
      client.workflows.triggerRun(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}

export function useCancelWorkflowRun() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => client.workflows.cancelRun(runId),
    onSuccess: (_, runId) => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.run(runId) });
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}

export function useRetryWorkflowRun() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => client.workflows.retryRun(runId),
    onSuccess: (_, runId) => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.run(runId) });
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}

export function usePauseWorkflowRun() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => client.workflows.pauseRun(runId),
    onSuccess: (_, runId) => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.run(runId) });
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}

export function useResumeWorkflowRun() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => client.workflows.resumeRun(runId),
    onSuccess: (_, runId) => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.run(runId) });
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}
