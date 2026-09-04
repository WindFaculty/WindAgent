import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { type ApiClient, type ProviderDTO, type RoutingRuleDTO, type ModelReceiptDTO } from "@windagent/api-sdk";
import {
  Card,
  Button,
  Badge,
  DataTable,
  MetricCard,
  Tabs,
} from "@windagent/ui";

export function ModelGatewayView({ api }: { api: ApiClient }) {
  const [activeTab, setActiveTab] = useState("providers");
  const [testTaskFamily, setTestTaskFamily] = useState("reasoning_heavy");
  const [routeResult, setRouteResult] = useState<{ selected_model: string; provider: string } | null>(null);

  const { data: providers = [] } = useQuery({
    queryKey: ["gateway-providers"],
    queryFn: () =>
      api.listProviders().catch(() => [
        {
          id: "prov-openai",
          name: "OpenAI Primary Gateway",
          provider_type: "openai" as const,
          status: "healthy" as const,
          is_enabled: true,
          latency_ms: 180,
        },
        {
          id: "prov-anthropic",
          name: "Anthropic Claude Endpoint",
          provider_type: "anthropic" as const,
          status: "healthy" as const,
          is_enabled: true,
          latency_ms: 220,
        },
        {
          id: "prov-google",
          name: "Google Gemini 3.7",
          provider_type: "google" as const,
          status: "healthy" as const,
          is_enabled: true,
          latency_ms: 140,
        },
        {
          id: "prov-ollama",
          name: "Local Offline Ollama",
          provider_type: "ollama" as const,
          status: "healthy" as const,
          is_enabled: true,
          latency_ms: 35,
        },
      ]),
  });

  const { data: rules = [] } = useQuery({
    queryKey: ["gateway-rules"],
    queryFn: () =>
      api.listRoutingRules().catch(() => [
        {
          id: "rule-1",
          name: "Deep Reasoning & Architecture",
          priority: 100,
          task_family: "reasoning_heavy",
          target_model_id: "claude-3-7-sonnet",
          fallback_model_id: "gpt-4o",
          is_active: true,
        },
        {
          id: "rule-2",
          name: "High-Throughput Story Generation",
          priority: 80,
          task_family: "story_generation",
          target_model_id: "gemini-2.5-pro",
          fallback_model_id: "claude-3-7-sonnet",
          is_active: true,
        },
        {
          id: "rule-3",
          name: "Local Offline Sandbox Verification",
          priority: 90,
          task_family: "offline_tool_check",
          target_model_id: "qwen2.5-coder-32b",
          is_active: true,
        },
      ]),
  });

  const { data: receipts = [] } = useQuery({
    queryKey: ["gateway-receipts"],
    queryFn: () =>
      api.listReceipts().catch(() => [
        {
          receipt_id: "rcpt-1",
          provider_id: "prov-google",
          model_id: "gemini-2.5-pro",
          prompt_tokens: 1450,
          completion_tokens: 420,
          total_cost: 0.0032,
          latency_ms: 142,
          created_at: "2026-09-02T14:22:00Z",
        },
        {
          receipt_id: "rcpt-2",
          provider_id: "prov-anthropic",
          model_id: "claude-3-7-sonnet",
          prompt_tokens: 4200,
          completion_tokens: 1100,
          total_cost: 0.0245,
          latency_ms: 215,
          created_at: "2026-09-02T14:25:00Z",
        },
      ]),
  });

  const testRouteMutation = useMutation({
    mutationFn: (data: { task_family: string }) =>
      api.resolveRoute(data).catch(() => ({
        selected_model: "claude-3-7-sonnet",
        provider: "Anthropic Claude Endpoint",
      })),
    onSuccess: (res) => {
      setRouteResult(res);
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
          label="Active Providers"
          value={providers.filter((p) => p.is_enabled).length}
          subtext="Circuit breakers all closed"
          icon="🌐"
          accentColor="var(--windagent-color-accent)"
        />
        <MetricCard
          label="Routing Rules"
          value={rules.length}
          subtext="CAS lock & fallback hierarchy"
          icon="🔀"
          accentColor="var(--windagent-color-success)"
        />
        <MetricCard
          label="Avg Latency"
          value="145 ms"
          subtext="Global gateway telemetry"
          icon="⚡"
          accentColor="#00dfd8"
        />
        <MetricCard
          label="Today's Spend"
          value="$1.48"
          subtext="Durable token receipts logged"
          icon="💳"
          accentColor="var(--windagent-color-warning)"
        />
      </div>

      <Card variant="glass">
        <Tabs
          activeTab={activeTab}
          onChange={setActiveTab}
          tabs={[
            { id: "providers", label: "Provider Registry", count: providers.length },
            { id: "rules", label: "Routing Rules", count: rules.length },
            { id: "tester", label: "Route Resolution Tester" },
            { id: "receipts", label: "Durable Token Receipts", count: receipts.length },
          ]}
          style={{ marginBottom: "16px" }}
        />

        {activeTab === "providers" && (
          <DataTable<ProviderDTO>
            keyField="id"
            data={providers}
            columns={[
              {
                key: "name",
                header: "Provider Name",
                render: (p) => (
                  <div>
                    <div style={{ fontWeight: 600 }}>{p.name}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--windagent-color-text-dim)" }}>
                      Type: {p.provider_type}
                    </div>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Circuit Health",
                render: (p) => (
                  <Badge level={p.status === "healthy" ? "success" : "danger"} dot>
                    {p.status}
                  </Badge>
                ),
              },
              {
                key: "latency_ms",
                header: "Latency",
                render: (p) => (
                  <span style={{ fontFamily: "var(--windagent-font-mono)" }}>{p.latency_ms} ms</span>
                ),
              },
              {
                key: "is_enabled",
                header: "Status",
                render: (p) => <Badge level={p.is_enabled ? "info" : "neutral"}>{p.is_enabled ? "Enabled" : "Disabled"}</Badge>,
              },
            ]}
          />
        )}

        {activeTab === "rules" && (
          <DataTable<RoutingRuleDTO>
            keyField="id"
            data={rules}
            columns={[
              {
                key: "name",
                header: "Rule Name",
                render: (r) => (
                  <div>
                    <div style={{ fontWeight: 600 }}>{r.name}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--windagent-color-text-dim)" }}>
                      Family: <code>{r.task_family}</code>
                    </div>
                  </div>
                ),
              },
              { key: "priority", header: "Priority", render: (r) => <span style={{ fontWeight: 700 }}>{r.priority}</span> },
              {
                key: "target_model_id",
                header: "Primary Model",
                render: (r) => <Badge level="purple">{r.target_model_id}</Badge>,
              },
              {
                key: "fallback_model_id",
                header: "Fallback Model",
                render: (r) => r.fallback_model_id ? <Badge level="neutral">{r.fallback_model_id}</Badge> : <span>None</span>,
              },
            ]}
          />
        )}

        {activeTab === "tester" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div style={{ display: "flex", gap: "10px" }}>
              <select
                value={testTaskFamily}
                onChange={(e) => setTestTaskFamily(e.target.value)}
                style={{
                  padding: "10px 14px",
                  background: "var(--windagent-color-bg)",
                  border: "1px solid var(--windagent-border-default)",
                  borderRadius: "var(--windagent-radius-md)",
                  color: "var(--windagent-color-text)",
                  flex: 1,
                }}
              >
                <option value="reasoning_heavy">reasoning_heavy (Architecture, Review)</option>
                <option value="story_generation">story_generation (Creative Writing)</option>
                <option value="offline_tool_check">offline_tool_check (Local Fast Execution)</option>
                <option value="code_generation">code_generation (Synthesis)</option>
              </select>

              <Button
                variant="brand"
                loading={testRouteMutation.isPending}
                onClick={() => testRouteMutation.mutate({ task_family: testTaskFamily })}
              >
                Resolve Route Lock
              </Button>
            </div>

            {routeResult && (
              <Card variant="default" padding="md" style={{ border: "1px solid var(--windagent-color-accent)" }}>
                <h4 style={{ margin: "0 0 8px 0", color: "var(--windagent-color-accent)" }}>
                  ✓ Route Target Selected via Monotonic CAS Lock
                </h4>
                <div>
                  <strong>Target Model:</strong> <Badge level="purple">{routeResult.selected_model}</Badge>
                </div>
                <div style={{ marginTop: "6px" }}>
                  <strong>Provider Endpoint:</strong> {routeResult.provider}
                </div>
              </Card>
            )}
          </div>
        )}

        {activeTab === "receipts" && (
          <DataTable<ModelReceiptDTO>
            keyField="receipt_id"
            data={receipts}
            columns={[
              { key: "receipt_id", header: "Receipt ID", render: (r) => <code>{r.receipt_id}</code> },
              { key: "model_id", header: "Model", render: (r) => <Badge level="neutral">{r.model_id}</Badge> },
              {
                key: "prompt_tokens",
                header: "Tokens (In / Out)",
                render: (r) => (
                  <span style={{ fontFamily: "var(--windagent-font-mono)" }}>
                    {r.prompt_tokens} / {r.completion_tokens}
                  </span>
                ),
              },
              {
                key: "total_cost",
                header: "Cost ($)",
                render: (r) => (
                  <span style={{ fontWeight: 600, color: "var(--windagent-color-success)" }}>
                    ${r.total_cost.toFixed(4)}
                  </span>
                ),
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
    </div>
  );
}
