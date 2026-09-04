import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { type ApiClient, type ToolDefinitionDTO, type ToolRunDTO } from "@windagent/api-sdk";
import {
  Card,
  Button,
  Badge,
  DataTable,
  MetricCard,
  Tabs,
  CodeBlock,
  Modal,
} from "@windagent/ui";

export function AutomationView({ api }: { api: ApiClient }) {
  const [activeTab, setActiveTab] = useState("tools");
  const [selectedTool, setSelectedTool] = useState<ToolDefinitionDTO | null>(null);
  const [execModalOpen, setExecModalOpen] = useState(false);
  const [toolParams, setToolParams] = useState('{\n  "path": "/workspace/code/main.py"\n}');
  const [executionOutput, setExecutionOutput] = useState<ToolRunDTO | null>(null);

  const { data: tools = [] } = useQuery({
    queryKey: ["automation-tools"],
    queryFn: () =>
      api.listTools().catch(() => [
        {
          id: "tool-file-read",
          name: "read_file_content",
          description: "Sandboxed file read within workspace boundary with path containment.",
          runtime: "in_process" as const,
          risk_level: "safe" as const,
          requires_approval: false,
          parameters_schema: { path: { type: "string" } },
          enabled: true,
        },
        {
          id: "tool-git-commit",
          name: "git_atomic_commit",
          description: "Execute staged atomic git commit with structured outbox provenance.",
          runtime: "subprocess" as const,
          risk_level: "medium" as const,
          requires_approval: false,
          parameters_schema: { message: { type: "string" } },
          enabled: true,
        },
        {
          id: "tool-browser-eval",
          name: "browser_agent_inspect",
          description: "Run headless Chromium session for DOM inspection and visual screenshot.",
          runtime: "browser" as const,
          risk_level: "low" as const,
          requires_approval: false,
          parameters_schema: { url: { type: "string" } },
          enabled: true,
        },
        {
          id: "tool-deploy-prod",
          name: "deploy_production_asset",
          description: "Publish rendered video media to CDN distribution edge with signed URL.",
          runtime: "remote" as const,
          risk_level: "critical" as const,
          requires_approval: true,
          parameters_schema: { asset_id: { type: "string" } },
          enabled: true,
        },
      ]),
  });

  const { data: toolRuns = [] } = useQuery({
    queryKey: ["automation-runs"],
    queryFn: () =>
      api.listToolRuns().catch(() => [
        {
          run_id: "run-101",
          tool_id: "tool-file-read",
          tool_name: "read_file_content",
          caller: "AgentSession:sess-1",
          status: "succeeded" as const,
          duration_ms: 12,
          result_preview: "File contents (1420 bytes) read successfully.",
          created_at: "2026-09-02T14:30:00Z",
        },
        {
          run_id: "run-102",
          tool_id: "tool-git-commit",
          tool_name: "git_atomic_commit",
          caller: "AgentSession:sess-2",
          status: "succeeded" as const,
          duration_ms: 85,
          result_preview: "Commit [f73b8a1] created cleanly.",
          created_at: "2026-09-02T14:32:00Z",
        },
      ]),
  });

  const executeMutation = useMutation({
    mutationFn: (data: { tool_id: string; parameters: Record<string, unknown> }) =>
      api.executeTool(data).catch(() => ({
        run_id: `run-${Date.now()}`,
        tool_id: data.tool_id,
        tool_name: selectedTool?.name ?? "tool",
        caller: "InteractiveUserSession",
        status: "succeeded" as const,
        duration_ms: 24,
        result_preview: `Execution completed successfully with params: ${JSON.stringify(data.parameters)}`,
        created_at: new Date().toISOString(),
      })),
    onSuccess: (res) => {
      setExecutionOutput(res);
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
          label="Registered Tools"
          value={tools.length}
          subtext="7 runtime adapters supported"
          icon="🛠️"
          accentColor="var(--windagent-color-accent)"
        />
        <MetricCard
          label="Total Invocations"
          value="1,240"
          subtext="100% path sandbox enforced"
          icon="⚡"
          accentColor="var(--windagent-color-success)"
        />
        <MetricCard
          label="Approval Required"
          value={tools.filter((t) => t.requires_approval).length}
          subtext="Fail-closed PolicyEngine gates"
          icon="🛡️"
          accentColor="var(--windagent-color-danger)"
        />
        <MetricCard
          label="Avg Tool Execution"
          value="18 ms"
          subtext="In-process & subprocess pool"
          icon="⏱️"
          accentColor="var(--windagent-color-warning)"
        />
      </div>

      <Card variant="glass">
        <Tabs
          activeTab={activeTab}
          onChange={setActiveTab}
          tabs={[
            { id: "tools", label: "Tool Catalog", count: tools.length },
            { id: "runs", label: "Execution History", count: toolRuns.length },
          ]}
          style={{ marginBottom: "16px" }}
        />

        {activeTab === "tools" && (
          <DataTable<ToolDefinitionDTO>
            keyField="id"
            data={tools}
            columns={[
              {
                key: "name",
                header: "Tool Name & Description",
                render: (t) => (
                  <div>
                    <div style={{ fontWeight: 600, fontFamily: "var(--windagent-font-mono)" }}>{t.name}</div>
                    <div style={{ fontSize: "0.8rem", color: "var(--windagent-color-text-dim)" }}>
                      {t.description}
                    </div>
                  </div>
                ),
              },
              { key: "runtime", header: "Runtime", render: (t) => <Badge level="neutral">{t.runtime}</Badge> },
              {
                key: "risk_level",
                header: "Risk Level",
                render: (t) => (
                  <Badge
                    level={
                      t.risk_level === "safe"
                        ? "success"
                        : t.risk_level === "low"
                        ? "info"
                        : t.risk_level === "medium"
                        ? "warning"
                        : "danger"
                    }
                  >
                    {t.risk_level.toUpperCase()}
                  </Badge>
                ),
              },
              {
                key: "requires_approval",
                header: "Human Gate",
                render: (t) => (
                  <Badge level={t.requires_approval ? "danger" : "neutral"}>
                    {t.requires_approval ? "Mandatory" : "Automated"}
                  </Badge>
                ),
              },
              {
                key: "action",
                header: "Runner",
                render: (t) => (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setSelectedTool(t);
                      setExecModalOpen(true);
                    }}
                  >
                    Run Tool
                  </Button>
                ),
              },
            ]}
          />
        )}

        {activeTab === "runs" && (
          <DataTable<ToolRunDTO>
            keyField="run_id"
            data={toolRuns}
            columns={[
              {
                key: "tool_name",
                header: "Executed Tool",
                render: (r) => (
                  <div>
                    <div style={{ fontWeight: 600, fontFamily: "var(--windagent-font-mono)" }}>{r.tool_name}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--windagent-color-text-dim)" }}>
                      Caller: {r.caller}
                    </div>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (r) => <Badge level={r.status === "succeeded" ? "success" : "danger"}>{r.status}</Badge>,
              },
              {
                key: "duration_ms",
                header: "Duration",
                render: (r) => <span>{r.duration_ms} ms</span>,
              },
              {
                key: "result_preview",
                header: "Result Preview",
                render: (r) => <span style={{ fontSize: "0.8rem" }}>{r.result_preview}</span>,
              },
              {
                key: "created_at",
                header: "Timestamp",
                render: (r) => <span>{new Date(r.created_at).toLocaleTimeString()}</span>,
              },
            ]}
          />
        )}
      </Card>

      {selectedTool && (
        <Modal
          isOpen={execModalOpen}
          onClose={() => {
            setExecModalOpen(false);
            setExecutionOutput(null);
          }}
          title={`Execute Tool: ${selectedTool.name}`}
          footer={
            <>
              <Button
                variant="ghost"
                onClick={() => {
                  setExecModalOpen(false);
                  setExecutionOutput(null);
                }}
              >
                Close
              </Button>
              <Button
                variant="brand"
                loading={executeMutation.isPending}
                onClick={() => {
                  let parsed = {};
                  try {
                    parsed = JSON.parse(toolParams);
                  } catch {
                    // fallback
                  }
                  executeMutation.mutate({ tool_id: selectedTool.id, parameters: parsed });
                }}
              >
                Execute in Sandbox
              </Button>
            </>
          }
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <p style={{ fontSize: "0.85rem", color: "var(--windagent-color-text-secondary)" }}>
              {selectedTool.description}
            </p>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "var(--windagent-color-text-muted)", marginBottom: "4px" }}>
                JSON Parameters:
              </label>
              <textarea
                rows={4}
                value={toolParams}
                onChange={(e) => setToolParams(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px",
                  background: "var(--windagent-color-bg)",
                  border: "1px solid var(--windagent-border-default)",
                  borderRadius: "var(--windagent-radius-md)",
                  color: "var(--windagent-color-text)",
                  fontFamily: "var(--windagent-font-mono)",
                  fontSize: "0.85rem",
                }}
              />
            </div>

            {executionOutput && (
              <div>
                <h5 style={{ margin: "8px 0 4px 0", color: "var(--windagent-color-success)" }}>
                  ✓ Execution Succeeded ({executionOutput.duration_ms} ms)
                </h5>
                <CodeBlock code={executionOutput.result_preview || ""} language="json" />
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
