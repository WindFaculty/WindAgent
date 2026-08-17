/**
 * Phase 11 — Agent Workspace Feature Hooks.
 * Provides query/mutation hooks for conversations, agent instances, task graphs,
 * and WebSocket streaming without aggressive polling loops.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type {
  ConversationDetailResource,
  AgentInstanceResource,
  TaskResource,
} from '@windagent/api-contracts';

export const agentWorkspaceKeys = {
  all: ['agent-workspace'] as const,
  conversation: (convId: string) => [...agentWorkspaceKeys.all, 'conversation', convId] as const,
  agents: (convId: string) => [...agentWorkspaceKeys.all, 'agents', convId] as const,
  tasks: (convId: string) => [...agentWorkspaceKeys.all, 'tasks', convId] as const,
  events: (convId: string) => [...agentWorkspaceKeys.all, 'events', convId] as const,
};

export function useConversation(conversationId: string) {
  const client = useApiClient();
  return useQuery<ConversationDetailResource>({
    queryKey: agentWorkspaceKeys.conversation(conversationId),
    queryFn: () => client.conversations.get(conversationId),
    enabled: Boolean(conversationId),
  });
}

export function useConversationAgents(conversationId: string) {
  const client = useApiClient();
  return useQuery<AgentInstanceResource[]>({
    queryKey: agentWorkspaceKeys.agents(conversationId),
    queryFn: () => client.conversations.getAgents(conversationId),
    enabled: Boolean(conversationId),
  });
}

export function useConversationTasks(conversationId: string) {
  const client = useApiClient();
  return useQuery<TaskResource[]>({
    queryKey: agentWorkspaceKeys.tasks(conversationId),
    queryFn: () => client.conversations.getTasks(conversationId),
    enabled: Boolean(conversationId),
  });
}

export function useConversationEvents(conversationId: string) {
  const client = useApiClient();
  return useQuery<Record<string, unknown>[]>({
    queryKey: agentWorkspaceKeys.events(conversationId),
    queryFn: () => client.conversations.getEvents(conversationId),
    enabled: Boolean(conversationId),
  });
}

export function useStopAgent(conversationId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) => client.conversations.stopAgent(conversationId, agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.agents(conversationId) });
      queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.conversation(conversationId) });
    },
  });
}

export function useCreateTask(conversationId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { objective: string; assigned_agent_instance_id?: string; dependencies?: string[]; concurrency_group?: string }) =>
      client.tasks.create({ conversation_id: conversationId, ...data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.tasks(conversationId) });
      queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.conversation(conversationId) });
    },
  });
}

export function useUpdateTask(conversationId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { taskId: string; data: { objective?: string; state?: string; expected_version: number } }) =>
      client.tasks.update(args.taskId, args.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.tasks(conversationId) });
      queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.conversation(conversationId) });
    },
  });
}

export function useCancelTask(conversationId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => client.tasks.cancel(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.tasks(conversationId) });
      queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.conversation(conversationId) });
    },
  });
}

export function useRetryTask(conversationId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => client.tasks.retry(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.tasks(conversationId) });
      queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.conversation(conversationId) });
    },
  });
}

/**
 * WebSocket Realtime Hook for Agent Workspace.
 * Connects to /ws/v3/agent-system and invalidates query caches on events.
 */
export function useAgentRealtime(conversationId: string) {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!conversationId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/v3/agent-system`;

    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type && payload.type.startsWith('agent.')) {
            queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.agents(conversationId) });
          } else if (payload.type && payload.type.startsWith('task.')) {
            queryClient.invalidateQueries({ queryKey: agentWorkspaceKeys.tasks(conversationId) });
          }
        } catch {
          // ignore non-json messages
        }
      };
    } catch {
      // ws fallback
    }

    return () => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
    };
  }, [conversationId, queryClient]);
}
