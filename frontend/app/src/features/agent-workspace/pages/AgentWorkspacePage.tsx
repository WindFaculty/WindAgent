import React, { useState } from 'react';
import {
  useConversation,
  useStopAgent,
  useCancelTask,
  useRetryTask,
  useAgentRealtime,
} from '../hooks/useAgentWorkspace';
import { CoordinatorPanel } from '../components/CoordinatorPanel';
import { AgentInstanceList } from '../components/AgentInstanceList';
import { TaskGraph } from '../components/TaskGraph';
import { AgentInspector } from '../components/AgentInspector';
import { AgentTerminal } from '../components/AgentTerminal';
import { BrowserRuntimePanel } from '../components/BrowserRuntimePanel';

interface AgentWorkspacePageProps {
  conversationId?: string;
}

export const AgentWorkspacePage: React.FC<AgentWorkspacePageProps> = ({
  conversationId = 'conv-default-01',
}) => {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  const { data: convDetail, isLoading, isError, error } = useConversation(conversationId);
  useAgentRealtime(conversationId);

  const stopAgentMutation = useStopAgent(conversationId);
  const cancelTaskMutation = useCancelTask(conversationId);
  const retryTaskMutation = useRetryTask(conversationId);

  if (isLoading) {
    return (
      <div style={{ padding: '32px', color: 'var(--text-muted, #9ca3af)', textAlign: 'center' }}>
        Loading agent workspace...
      </div>
    );
  }

  if (isError || !convDetail) {
    return (
      <div style={{ padding: '32px', color: '#ef4444' }}>
        Failed to load conversation: {error ? String(error) : 'Not found'}
      </div>
    );
  }

  const { conversation, agents, tasks, events } = convDetail;
  const selectedAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];

  return (
    <div
      style={{
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        maxWidth: '1600px',
        margin: '0 auto',
        fontFamily: 'var(--font-sans, sans-serif)',
      }}
    >
      <CoordinatorPanel conversation={conversation} />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(320px, 1fr) minmax(400px, 1.6fr) minmax(320px, 1.2fr)',
          gap: '20px',
          alignItems: 'start',
        }}
      >
        {/* Left column: Agent Instances List & Browser */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <AgentInstanceList
            agents={agents}
            selectedAgentId={selectedAgent?.id}
            onSelectAgent={(id) => setSelectedAgentId(id)}
            onStopAgent={(id) => stopAgentMutation.mutate(id)}
          />
          <BrowserRuntimePanel />
        </div>

        {/* Center column: Task Graph */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <TaskGraph
            tasks={tasks}
            onCancelTask={(id) => cancelTaskMutation.mutate(id)}
            onRetryTask={(id) => retryTaskMutation.mutate(id)}
          />
        </div>

        {/* Right column: Agent Inspector & Terminal */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <AgentInspector agent={selectedAgent} />
          <AgentTerminal events={events} />
        </div>
      </div>
    </div>
  );
};
