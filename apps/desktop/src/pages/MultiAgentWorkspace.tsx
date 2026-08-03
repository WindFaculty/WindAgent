import { useEffect, useMemo, useState } from "react";
import {
  fetchBrowserState,
  resolveApiUrl,
  stopConversationAgent,
  type AgentBoardRow,
  type BrowserState,
  type TaskGraphNode,
} from "../api/client";
import { useMultiAgent } from "../state/multiAgentStore";

const panelStyle: React.CSSProperties = {
  background: "var(--bg-panel)",
  border: "1px solid var(--border-color)",
  borderRadius: 12,
  minWidth: 0,
  padding: 16,
};

function labelForAgent(agent: AgentBoardRow | undefined): string {
  if (!agent) return "Chưa có agent điều phối";
  return agent.agent_type === "orchestrator" ? "Agent điều phối" : agent.agent_type;
}

function profileLabel(profile: Record<string, unknown>): string {
  const values = Object.entries(profile)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" · ");
  return values || "Chưa gán quyền riêng";
}

function BrowserPanel({ browserSessionId }: { browserSessionId: string | undefined }) {
  const [browser, setBrowser] = useState<BrowserState | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    if (!browserSessionId) {
      setBrowser(null);
      setUnavailable(false);
      return;
    }
    let active = true;
    const refresh = async () => {
      try {
        const next = await fetchBrowserState(browserSessionId);
        if (active) {
          setBrowser(next);
          setUnavailable(false);
        }
      } catch {
        if (active) {
          setBrowser(null);
          setUnavailable(true);
        }
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 2_000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [browserSessionId]);

  if (!browserSessionId || unavailable) {
    return <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Không có browser runtime.</p>;
  }
  if (!browser) return <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Đang tải browser session…</p>;

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", overflowWrap: "anywhere" }}>
        {browser.title || browser.url}
      </div>
      {browser.screenshot_url ? (
        <img
          src={resolveApiUrl(browser.screenshot_url)}
          alt={`Browser session ${browser.session_id}`}
          style={{ width: "100%", borderRadius: 8, border: "1px solid var(--border-color)" }}
        />
      ) : (
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Browser chưa có screenshot.</p>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div style={{ display: "grid", gap: 2 }}>
      <span style={{ color: "var(--text-muted)", fontSize: "0.7rem", textTransform: "uppercase" }}>{label}</span>
      <span style={{ fontSize: "0.8rem", overflowWrap: "anywhere" }}>{value || "—"}</span>
    </div>
  );
}

/** Phase 7 production workspace: one view over durable conversation projections. */
export function MultiAgentWorkspace({ conversationId }: { conversationId: string }) {
  const { state, select, refresh } = useMultiAgent();
  const [stopError, setStopError] = useState<string | null>(null);
  const conversation = state.conversations[conversationId];

  const agents = useMemo(
    () => (conversation?.agentInstanceIds ?? []).map((id) => state.agents[id]).filter(Boolean),
    [conversation?.agentInstanceIds, state.agents],
  );
  const coordinator = agents.find((agent) => agent.agent_type === "orchestrator");
  const subAgents = agents.filter((agent) => agent.agent_type !== "orchestrator");
  const selected = state.selectedAgentId ? state.agents[state.selectedAgentId] : undefined;
  const activePlanId = conversation?.planVersionIds.at(-1);
  const nodes = activePlanId ? Object.values(state.taskNodes[activePlanId] ?? {}) : [];
  const selectedTask = selected?.assigned_node_id
    ? state.taskNodes[activePlanId ?? ""]?.[selected.assigned_node_id]
    : undefined;
  const terminalLines = selected ? state.events[selected.agent_instance_id]?.lines ?? [] : [];
  const browserSessionId = selected ? state.browserSessionIds[selected.agent_instance_id] : undefined;

  const stopSelected = async () => {
    if (!selected || !conversationId) return;
    try {
      setStopError(null);
      await stopConversationAgent(conversationId, selected.agent_instance_id);
      await refresh();
    } catch (error) {
      setStopError(error instanceof Error ? error.message : "Không thể dừng agent.");
    }
  };

  return (
    <main className="central-workspace multi-agent-wrapper" aria-label="Multi-agent workspace">
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.2rem" }}>Workspace đa tác tử</h1>
          <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Conversation: {conversationId}</span>
        </div>
        <button className="role-btn" onClick={() => void refresh()}>Làm mới</button>
      </header>

      <div className="multi-agent-grid" style={{ gridTemplateColumns: "minmax(220px, .9fr) minmax(280px, 1.15fr) minmax(300px, 1.35fr)", alignItems: "start" }}>
        <section style={panelStyle} aria-labelledby="coordinator-heading">
          <h2 id="coordinator-heading" style={{ marginTop: 0, fontSize: "1rem" }}>Agent điều phối</h2>
          {coordinator ? (
            <div style={{ display: "grid", gap: 12 }}>
              <strong>{labelForAgent(coordinator)}</strong>
              <Field label="Trạng thái" value={coordinator.status} />
              <Field label="Model" value={coordinator.canonical_model_id} />
              <Field label="Session" value={coordinator.agent_session_id} />
              <Field label="Quyền" value={profileLabel(coordinator.permission_profile)} />
            </div>
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Chưa có điều phối viên cho conversation này.</p>
          )}
        </section>

        <section style={panelStyle} aria-labelledby="agents-heading">
          <h2 id="agents-heading" style={{ marginTop: 0, fontSize: "1rem" }}>Sub-agents</h2>
          <div style={{ display: "grid", gap: 8, marginBottom: 18 }}>
            {subAgents.length === 0 && <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Chưa có sub-agent.</p>}
            {subAgents.map((agent) => {
              const active = agent.agent_instance_id === selected?.agent_instance_id;
              return (
                <button
                  key={agent.agent_instance_id}
                  onClick={() => select(agent.agent_instance_id)}
                  style={{
                    textAlign: "left", cursor: "pointer", borderRadius: 8, padding: 10,
                    border: `1px solid ${active ? "var(--color-primary)" : "var(--border-color)"}`,
                    background: active ? "rgba(59, 130, 246, .12)" : "transparent", color: "inherit",
                  }}
                >
                  <strong>{agent.agent_type}</strong>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, color: "var(--text-muted)", fontSize: "0.76rem", marginTop: 4 }}>
                    <span>{agent.node_state ?? agent.status}</span>
                    <span>{agent.current_tool_name ?? agent.planned_tool_name ?? "Không có tool đang chạy"}</span>
                  </div>
                </button>
              );
            })}
          </div>

          <h2 style={{ fontSize: "1rem", margin: "0 0 8px" }}>Công việc hiện tại</h2>
          <div style={{ display: "grid", gap: 8 }}>
            {nodes.length === 0 && <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Chưa có kế hoạch bền vững.</p>}
            {nodes.map((node) => <TaskRow key={node.node_id} node={node} selected={node.node_id === selectedTask?.node_id} />)}
          </div>
        </section>

        <section style={panelStyle} aria-labelledby="inspector-heading">
          <h2 id="inspector-heading" style={{ marginTop: 0, fontSize: "1rem" }}>Inspector</h2>
          {!selected ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Chọn một sub-agent để xem thông tin thực thi.</p>
          ) : (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <strong>{selected.agent_type}</strong>
                {selected.agent_run_status === "running" && <button className="btn-danger-action" onClick={() => void stopSelected}>Dừng agent</button>}
              </div>
              {stopError && <p role="alert" style={{ color: "var(--color-danger, #ef4444)", fontSize: "0.8rem" }}>{stopError}</p>}
              <div style={{ display: "grid", gap: 10 }}>
                <Field label="Model" value={selected.canonical_model_id} />
                <Field label="Provider binding" value={selected.provider_binding_id} />
                <Field label="Route lock" value={selected.route_lock_id} />
                <Field label="Công việc" value={selectedTask?.objective} />
                <Field label="Permission profile" value={profileLabel(selected.permission_profile)} />
                <Field label="Tool đang chạy" value={selected.current_tool_name ?? selected.planned_tool_name} />
                <Field label="Worktree" value={selected.worktree_path} />
                <Field label="Nhánh worktree" value={selected.worktree_branch} />
              </div>

              <h3 style={{ fontSize: "0.9rem", margin: "18px 0 8px" }}>Terminal</h3>
              <pre style={{ margin: 0, maxHeight: 160, overflow: "auto", padding: 10, borderRadius: 8, background: "rgba(0,0,0,.25)", fontSize: "0.75rem", whiteSpace: "pre-wrap" }}>
                {terminalLines.length ? terminalLines.join("\n") : "Chưa có terminal output từ agent này."}
              </pre>

              <h3 style={{ fontSize: "0.9rem", margin: "18px 0 8px" }}>Browser session</h3>
              <BrowserPanel browserSessionId={browserSessionId} />
            </>
          )}
        </section>
      </div>
    </main>
  );
}

function TaskRow({ node, selected }: { node: TaskGraphNode; selected: boolean }) {
  return (
    <div style={{ borderLeft: `3px solid ${selected ? "var(--color-primary)" : "var(--border-color)"}`, padding: "7px 9px", background: "rgba(255,255,255,.02)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <strong style={{ fontSize: "0.82rem" }}>{node.objective || node.node_id}</strong>
        <span style={{ color: "var(--text-muted)", fontSize: "0.74rem" }}>{node.status}</span>
      </div>
      <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: 3 }}>
        {node.agent_type ?? "agent"} · {node.tool_name ?? "không có tool"}
        {node.concurrency_group ? ` · ${node.concurrency_group}` : ""}
      </div>
    </div>
  );
}
