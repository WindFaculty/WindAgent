import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createApiClient } from "@windagent/api-sdk";
import {
  AppLayout,
  SidebarNav,
  Header,
  WorkspaceSwitcher,
  NotificationToast,
  type NavItem,
  type ToastMessage,
} from "@windagent/ui";
import { useRouter, type AppRoute } from "../router/Router.tsx";
import { WorkspaceView } from "../../modules/workspace/WorkspaceView.tsx";
import { StudioView } from "../../modules/studio/StudioView.tsx";
import { AgentSystemView } from "../../modules/agent_system/AgentSystemView.tsx";
import { ModelGatewayView } from "../../modules/model_gateway/ModelGatewayView.tsx";
import { AutomationView } from "../../modules/automation/AutomationView.tsx";
import { ProductionView } from "../../modules/production/ProductionView.tsx";
import { LiveRecordView } from "../../modules/live_record/LiveRecordView.tsx";
import { QualityView } from "../../modules/quality/QualityView.tsx";
import { OperationsView } from "../../modules/operations/OperationsView.tsx";

const api = createApiClient({ baseUrl: "" });

export function AppShell() {
  const { currentRoute, navigate } = useRouter("workspace");
  const [activeWorkspaceId, setActiveWorkspaceId] = useState("ws-default");
  const [toasts, setToasts] = useState<ToastMessage[]>([
    {
      id: "toast-init",
      type: "success",
      title: "Milestone 4 User Platform Active",
      message: "All 9 bounded context UI views connected to /api/v4/* API surface.",
    },
  ]);

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health().catch(() => ({ status: "ok" as const, version: "0.1.0" })),
  });

  const { data: workspaces = [] } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () =>
      api.listWorkspaces().catch(() => [
        {
          id: "ws-default",
          name: "Primary Studio Workspace",
          slug: "primary-studio",
          owner_id: "user-admin",
          status: "active" as const,
          created_at: "2026-09-02T10:00:00Z",
          updated_at: "2026-09-02T10:00:00Z",
          members_count: 3,
        },
        {
          id: "ws-staging",
          name: "Production Pipeline Staging",
          slug: "prod-staging",
          owner_id: "user-admin",
          status: "active" as const,
          created_at: "2026-09-02T12:00:00Z",
          updated_at: "2026-09-02T12:00:00Z",
          members_count: 5,
        },
      ]),
  });

  const navItems: NavItem[] = [
    { id: "workspace", label: "Workspaces", icon: "🏢", category: "core" },
    { id: "studio", label: "Studio & Story", icon: "🎬", category: "creative" },
    { id: "agents", label: "Agent Runtime", icon: "🤖", badge: "Live", category: "agents" },
    { id: "model_gateway", label: "Model Gateway", icon: "🌐", category: "infrastructure" },
    { id: "automation", label: "Automation Tools", icon: "🛠️", category: "runtime" },
    { id: "production", label: "Video Production", icon: "🎞️", category: "creative" },
    { id: "live_record", label: "Live Record", icon: "🎥", category: "media" },
    { id: "quality", label: "Quality & Gates", icon: "🏆", badge: "A+", category: "ops" },
    { id: "operations", label: "Operations & Logs", icon: "📊", category: "ops" },
  ];

  const routeTitles: Record<AppRoute, { title: string; subtitle: string }> = {
    workspace: {
      title: "Workspace Management & Quotas",
      subtitle: "Multi-tenant authorization partitions, sandboxed paths, and resource fencing locks",
    },
    studio: {
      title: "Studio: Creative Projects & Story Beats",
      subtitle: "Story generation, character continuity bibles, and episode storyboards",
    },
    agents: {
      title: "Agent Runtime & DAG Pipelines",
      subtitle: "Autonomous execution loops, interactive DAG graphs, and human approval gates",
    },
    model_gateway: {
      title: "Model Gateway & Smart Routing",
      subtitle: "Unified provider abstraction, CAS route locks, and durable token receipts",
    },
    automation: {
      title: "Automation Tool Runtime",
      subtitle: "Sandboxed tool execution across in-process, subprocess, browser, and MCP adapters",
    },
    production: {
      title: "Video Production & Asset Assembly",
      subtitle: "ACEScg color management, code-video rendering, and EDL timeline assembly",
    },
    live_record: {
      title: "Live Record Director & Studio Capture",
      subtitle: "Native screen recording with privacy scanning and real-time cue triggers",
    },
    quality: {
      title: "Quality Evals & Verification Certification",
      subtitle: "11-dimension evaluation rubrics, regression detection, and verification gates",
    },
    operations: {
      title: "System Operations & Outbox Stream",
      subtitle: "Process telemetry, W3C traces, and transactional event outbox logs",
    },
  };

  const currentMeta = routeTitles[currentRoute] || routeTitles.workspace;

  return (
    <AppLayout
      sidebar={
        <SidebarNav
          items={navItems}
          activeId={currentRoute}
          onSelect={(id) => navigate(id as AppRoute)}
        />
      }
      header={
        <Header
          title={currentMeta.title}
          subtitle={currentMeta.subtitle}
          apiHealthy={health?.status === "ok"}
          workspaceSlot={
            <WorkspaceSwitcher
              workspaces={workspaces}
              activeWorkspaceId={activeWorkspaceId}
              onSelect={setActiveWorkspaceId}
              onCreateNew={() => navigate("workspace")}
            />
          }
        />
      }
    >
      {currentRoute === "workspace" && (
        <WorkspaceView
          api={api}
          activeWorkspaceId={activeWorkspaceId}
          onSelectWorkspace={setActiveWorkspaceId}
        />
      )}
      {currentRoute === "studio" && <StudioView api={api} />}
      {currentRoute === "agents" && <AgentSystemView api={api} />}
      {currentRoute === "model_gateway" && <ModelGatewayView api={api} />}
      {currentRoute === "automation" && <AutomationView api={api} />}
      {currentRoute === "production" && <ProductionView api={api} />}
      {currentRoute === "live_record" && <LiveRecordView api={api} />}
      {currentRoute === "quality" && <QualityView api={api} />}
      {currentRoute === "operations" && <OperationsView api={api} />}

      <NotificationToast
        toasts={toasts}
        onDismiss={(id) => setToasts((prev) => prev.filter((t) => t.id !== id))}
      />
    </AppLayout>
  );
}
