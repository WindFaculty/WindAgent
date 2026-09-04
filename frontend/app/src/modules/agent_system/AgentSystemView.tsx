import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { type ApiClient, type AgentSessionDTO, type ApprovalRequestDTO, type MemoryRecordDTO } from "@windagent/api-sdk";
import {
  Card,
  Button,
  Badge,
  DataTable,
  MetricCard,
  Modal,
  Tabs,
  GraphViewer,
  type GraphNode,
} from "@windagent/ui";

export function AgentSystemView({ api }: { api: ApiClient }) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState("sessions");
  const [selectedSessionId, setSelectedSessionId] = useState("sess-1");
  const [approvalModalOpen, setApprovalModalOpen] = useState(false);
  const [activeApproval, setActiveApproval] = useState<ApprovalRequestDTO | null>(null);

  const { data: sessions = [] } = useQuery({
    queryKey: ["agent-sessions"],
    queryFn: () =>
      api.listSessions().catch(() => [
        {
          id: "sess-1",
          title: "Autonomous Video Rendering & Review",
          agent_name: "Lead Production Director",
          status: "active" as const,
          budget_remaining: 85000,
          total_steps: 14,
          created_at: "2026-09-02T14:00:00Z",
          updated_at: "2026-09-02T14:20:00Z",
        },
        {
          id: "sess-2",
          title: "Code Refactoring & Unit Test Synthesis",
          agent_name: "Senior Software Architect",
          status: "completed" as const,
          budget_remaining: 120000,
          total_steps: 28,
          created_at: "2026-09-02T12:00:00Z",
          updated_at: "2026-09-02T12:45:00Z",
        },
      ]),
  });

  const { data: approvals = [] } = useQuery({
    queryKey: ["agent-approvals"],
    queryFn: () =>
      api.listApprovals().catch(() => [
        {
          id: "appr-1",
          session_id: "sess-1",
          action_name: "deploy_video_production_render",
          risk_level: "high" as const,
          description: "High GPU compute allocation for 4K scene rendering (estimated 120 credits)",
          parameters: { project_id: "proj-1", shots_count: 8, resolution: "3840x2160" },
          status: "pending" as const,
          created_at: "2026-09-02T14:15:00Z",
        },
      ]),
  });

  const { data: memoryRecords = [] } = useQuery({
    queryKey: ["memory-records"],
    queryFn: () =>
      api.listMemoryRecords().catch(() => [
        {
          id: "mem-1",
          scope: "project" as const,
          key: "style_guide_colorspace",
          content: "Enforce ACEScg wide color gamut with Rec.709 sRGB display transformation.",
          confidence: 0.98,
          status: "promoted" as const,
          provenance: "ADR-0007-production",
          created_at: "2026-09-02T09:00:00Z",
        },
        {
          id: "mem-2",
          scope: "procedural" as const,
          key: "failure_retry_policy",
          content: "When ffmpeg NVENC buffer fills, fallback gracefully to CPU libx264 with crf 18.",
          confidence: 0.92,
          status: "validated" as const,
          provenance: "LiveRecordEngine",
          created_at: "2026-09-02T09:30:00Z",
        },
      ]),
  });

  const resolveApprovalMutation = useMutation({
    mutationFn: ({ id, approved }: { id: string; approved: boolean }) =>
      api.resolveApproval(id, approved).catch(() => ({
        id,
        session_id: selectedSessionId,
        action_name: "deploy_video_production_render",
        risk_level: "high" as const,
        description: "",
        parameters: {},
        status: approved ? ("approved" as const) : ("rejected" as const),
        created_at: "2026-09-02T14:15:00Z",
      })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent-approvals"] });
      setApprovalModalOpen(false);
      setActiveApproval(null);
    },
  });

  const workflowNodes: GraphNode[] = [
    { id: "node-1", label: "Context Assembly", type: "ContextEngine", status: "completed" },
    { id: "node-2", label: "Script Analysis", type: "ModelGateway", status: "completed" },
    { id: "node-3", label: "Asset Generation", type: "AutomationTool", status: "running" },
    { id: "node-4", label: "Quality Evaluation", type: "QualityGate", status: "pending" },
    { id: "node-5", label: "EDL Assembly", type: "ProductionEngine", status: "pending" },
  ];

  const workflowEdges = [
    { from: "node-1", to: "node-2" },
    { from: "node-2", to: "node-3" },
    { from: "node-3", to: "node-4" },
    { from: "node-4", to: "node-5" },
  ];

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
          label="Active Sessions"
          value={sessions.filter((s) => s.status === "active").length}
          subtext="Autonomous runtime loops"
          icon="🤖"
          accentColor="var(--windagent-color-accent)"
        />
        <MetricCard
          label="Human Approvals"
          value={approvals.filter((a) => a.status === "pending").length}
          subtext="High-risk action gates"
          icon="🛡️"
          accentColor="var(--windagent-color-danger)"
        />
        <MetricCard
          label="Memory Bank Records"
          value={memoryRecords.length}
          subtext="Validated episodic & semantic items"
          icon="🧠"
          accentColor="#d2a8ff"
        />
        <MetricCard
          label="Avg Context Budget"
          value="85k tokens"
          subtext="Dynamic budgeting active"
          icon="⚡"
          accentColor="var(--windagent-color-success)"
        />
      </div>

      <Card variant="glass">
        <Tabs
          activeTab={activeTab}
          onChange={setActiveTab}
          tabs={[
            { id: "sessions", label: "Agent Sessions", count: sessions.length },
            { id: "dag", label: "Workflow DAG Inspector" },
            { id: "approvals", label: "Approval Center", count: approvals.filter((a) => a.status === "pending").length },
            { id: "memory", label: "Memory Knowledge Bank", count: memoryRecords.length },
          ]}
          style={{ marginBottom: "16px" }}
        />

        {activeTab === "sessions" && (
          <DataTable<AgentSessionDTO>
            keyField="id"
            data={sessions}
            onRowClick={(s) => setSelectedSessionId(s.id)}
            columns={[
              {
                key: "title",
                header: "Session Title",
                render: (s) => (
                  <div>
                    <div style={{ fontWeight: 600 }}>{s.title}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--windagent-color-text-dim)" }}>
                      Agent: {s.agent_name}
                    </div>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (s) => (
                  <Badge level={s.status === "active" ? "info" : "success"} dot>
                    {s.status}
                  </Badge>
                ),
              },
              {
                key: "budget_remaining",
                header: "Budget Remaining",
                render: (s) => (
                  <span style={{ fontFamily: "var(--windagent-font-mono)" }}>
                    {s.budget_remaining.toLocaleString()} tokens
                  </span>
                ),
              },
              {
                key: "total_steps",
                header: "Steps Executed",
                render: (s) => <span>{s.total_steps} steps</span>,
              },
            ]}
          />
        )}

        {activeTab === "dag" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <h4 style={{ margin: 0, fontSize: "0.95rem" }}>DAG Pipeline: Autonomous Production Run</h4>
                <span style={{ fontSize: "0.8rem", color: "var(--windagent-color-text-dim)" }}>
                  Session ID: {selectedSessionId}
                </span>
              </div>
              <Badge level="info" dot>Running</Badge>
            </div>

            <GraphViewer nodes={workflowNodes} edges={workflowEdges} />
          </div>
        )}

        {activeTab === "approvals" && (
          <DataTable<ApprovalRequestDTO>
            keyField="id"
            data={approvals}
            columns={[
              {
                key: "action_name",
                header: "Action / Tool",
                render: (a) => (
                  <div>
                    <div style={{ fontWeight: 600 }}>{a.action_name}</div>
                    <div style={{ fontSize: "0.8rem", color: "var(--windagent-color-text-muted)" }}>
                      {a.description}
                    </div>
                  </div>
                ),
              },
              {
                key: "risk_level",
                header: "Risk Level",
                render: (a) => <Badge level="danger">{a.risk_level.toUpperCase()}</Badge>,
              },
              {
                key: "status",
                header: "Decision",
                render: (a) => (
                  <Badge level={a.status === "pending" ? "warning" : a.status === "approved" ? "success" : "danger"}>
                    {a.status}
                  </Badge>
                ),
              },
              {
                key: "actions",
                header: "Actions",
                render: (a) =>
                  a.status === "pending" ? (
                    <div style={{ display: "flex", gap: "8px" }}>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => {
                          setActiveApproval(a);
                          setApprovalModalOpen(true);
                        }}
                      >
                        Review
                      </Button>
                    </div>
                  ) : (
                    <span style={{ color: "var(--windagent-color-text-dim)" }}>Resolved</span>
                  ),
              },
            ]}
          />
        )}

        {activeTab === "memory" && (
          <DataTable<MemoryRecordDTO>
            keyField="id"
            data={memoryRecords}
            columns={[
              {
                key: "key",
                header: "Memory Key & Provenance",
                render: (m) => (
                  <div>
                    <div style={{ fontWeight: 600, fontFamily: "var(--windagent-font-mono)" }}>{m.key}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--windagent-color-text-dim)" }}>
                      Source: {m.provenance}
                    </div>
                  </div>
                ),
              },
              { key: "scope", header: "Scope", render: (m) => <Badge level="purple">{m.scope}</Badge> },
              {
                key: "content",
                header: "Knowledge Payload",
                render: (m) => <span style={{ fontSize: "0.85rem" }}>{m.content}</span>,
              },
              {
                key: "status",
                header: "Status",
                render: (m) => <Badge level="success">{m.status}</Badge>,
              },
            ]}
          />
        )}
      </Card>

      {activeApproval && (
        <Modal
          isOpen={approvalModalOpen}
          onClose={() => setApprovalModalOpen(false)}
          title="Review High-Risk Agent Action"
          footer={
            <>
              <Button
                variant="danger"
                loading={resolveApprovalMutation.isPending}
                onClick={() => resolveApprovalMutation.mutate({ id: activeApproval.id, approved: false })}
              >
                Reject Action
              </Button>
              <Button
                variant="primary"
                loading={resolveApprovalMutation.isPending}
                onClick={() => resolveApprovalMutation.mutate({ id: activeApproval.id, approved: true })}
              >
                Authorize Execution
              </Button>
            </>
          }
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div>
              <strong>Action Name:</strong> <code>{activeApproval.action_name}</code>
            </div>
            <div>
              <strong>Risk Classification:</strong> <Badge level="danger">{activeApproval.risk_level.toUpperCase()}</Badge>
            </div>
            <div>
              <strong>Description:</strong> {activeApproval.description}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
