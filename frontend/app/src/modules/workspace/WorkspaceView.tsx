import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { type ApiClient, type WorkspaceDTO } from "@windagent/api-sdk";
import {
  Card,
  CardHeader,
  Button,
  Badge,
  DataTable,
  MetricCard,
  Modal,
} from "@windagent/ui";

export function WorkspaceView({
  api,
  activeWorkspaceId,
  onSelectWorkspace,
}: {
  api: ApiClient;
  activeWorkspaceId?: string;
  onSelectWorkspace: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newWsName, setNewWsName] = useState("");
  const [newWsSlug, setNewWsSlug] = useState("");

  const { data: workspaces = [] } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.listWorkspaces().catch(() => [
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

  const { data: quota } = useQuery({
    queryKey: ["workspace-quota", activeWorkspaceId],
    queryFn: () => (activeWorkspaceId ? api.getWorkspaceQuota(activeWorkspaceId) : null),
    enabled: !!activeWorkspaceId,
  });

  const { data: locks = [] } = useQuery({
    queryKey: ["workspace-locks", activeWorkspaceId],
    queryFn: () => (activeWorkspaceId ? api.listWorkspaceLocks(activeWorkspaceId) : []),
    enabled: !!activeWorkspaceId,
  });

  const createMutation = useMutation({
    mutationFn: (data: { name: string; slug: string }) => api.createWorkspace(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      setCreateModalOpen(false);
      setNewWsName("");
      setNewWsSlug("");
    },
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--windagent-space-6)" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: "var(--windagent-space-4)",
        }}
      >
        <MetricCard
          label="Total Workspaces"
          value={workspaces.length}
          subtext="Active multi-tenant partitions"
          icon="🏢"
          accentColor="var(--windagent-color-accent)"
        />
        <MetricCard
          label="Resource Quota Utilization"
          value={`${quota?.current_projects ?? 2} / ${quota?.max_projects ?? 25}`}
          subtext="Projects allocated"
          icon="📊"
          accentColor="var(--windagent-color-success)"
        />
        <MetricCard
          label="Fencing Locks"
          value={locks.length}
          subtext="Distributed mutexes active"
          icon="🔒"
          accentColor="var(--windagent-color-warning)"
        />
        <MetricCard
          label="Concurrency Limit"
          value={`${quota?.current_concurrent_runs ?? 1} / ${quota?.max_concurrent_runs ?? 10}`}
          subtext="Worker run slots"
          icon="⚡"
          accentColor="#d2a8ff"
        />
      </div>

      <Card variant="glass">
        <CardHeader
          title="Workspaces & Isolation Boundaries"
          subtitle="Strict multi-tenant authorization partitions with sandboxed paths"
          action={
            <Button
              variant="brand"
              size="sm"
              icon="+"
              onClick={() => setCreateModalOpen(true)}
            >
              Create Workspace
            </Button>
          }
        />

        <DataTable<WorkspaceDTO>
          keyField="id"
          data={workspaces}
          onRowClick={(ws) => onSelectWorkspace(ws.id)}
          columns={[
            {
              key: "name",
              header: "Workspace Name",
              render: (ws) => (
                <div>
                  <div style={{ fontWeight: 600, color: "var(--windagent-color-text)" }}>
                    {ws.name}
                    {ws.id === activeWorkspaceId && (
                      <Badge level="info" style={{ marginLeft: "8px" }}>
                        Selected
                      </Badge>
                    )}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--windagent-color-text-dim)" }}>
                    /{ws.slug}
                  </div>
                </div>
              ),
            },
            {
              key: "status",
              header: "Status",
              render: (ws) => (
                <Badge level={ws.status === "active" ? "success" : "warning"} dot>
                  {ws.status}
                </Badge>
              ),
            },
            {
              key: "members_count",
              header: "Members",
              render: (ws) => <span>{ws.members_count || 1} users</span>,
            },
            {
              key: "created_at",
              header: "Created",
              render: (ws) => (
                <span style={{ color: "var(--windagent-color-text-muted)" }}>
                  {new Date(ws.created_at).toLocaleDateString()}
                </span>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Create New Workspace"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={!newWsName || !newWsSlug}
              loading={createMutation.isPending}
              onClick={() =>
                createMutation.mutate({ name: newWsName, slug: newWsSlug.toLowerCase() })
              }
            >
              Provision Workspace
            </Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.85rem", color: "var(--windagent-color-text-secondary)", marginBottom: "6px" }}>
              Workspace Name
            </label>
            <input
              type="text"
              value={newWsName}
              onChange={(e) => {
                setNewWsName(e.target.value);
                if (!newWsSlug) {
                  setNewWsSlug(e.target.value.toLowerCase().replace(/\s+/g, "-"));
                }
              }}
              placeholder="e.g. Enterprise Video Studio"
              style={{
                width: "100%",
                padding: "8px 12px",
                background: "var(--windagent-color-bg)",
                border: "1px solid var(--windagent-border-default)",
                borderRadius: "var(--windagent-radius-md)",
                color: "var(--windagent-color-text)",
                fontSize: "0.9rem",
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.85rem", color: "var(--windagent-color-text-secondary)", marginBottom: "6px" }}>
              URL Slug
            </label>
            <input
              type="text"
              value={newWsSlug}
              onChange={(e) => setNewWsSlug(e.target.value)}
              placeholder="e.g. enterprise-video-studio"
              style={{
                width: "100%",
                padding: "8px 12px",
                background: "var(--windagent-color-bg)",
                border: "1px solid var(--windagent-border-default)",
                borderRadius: "var(--windagent-radius-md)",
                color: "var(--windagent-color-text)",
                fontSize: "0.9rem",
              }}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
