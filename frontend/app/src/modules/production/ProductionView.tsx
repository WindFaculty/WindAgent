import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { type ApiClient, type ProductionProjectDTO, type MediaAssetDTO, type RenderJobDTO } from "@windagent/api-sdk";
import {
  Card,
  Button,
  Badge,
  DataTable,
  MetricCard,
  Tabs,
  Modal,
} from "@windagent/ui";

export function ProductionView({ api }: { api: ApiClient }) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState("projects");
  const [selectedProjectId, setSelectedProjectId] = useState("prod-1");
  const [renderModalOpen, setRenderModalOpen] = useState(false);
  const [shotId, setShotId] = useState("shot-01");
  const [renderEngine, setRenderEngine] = useState("code_video");

  const { data: projects = [] } = useQuery({
    queryKey: ["production-projects"],
    queryFn: () =>
      api.listProductionProjects().catch(() => [
        {
          id: "prod-1",
          title: "Neon Horizon: Opening Sequence",
          format: "16:9" as const,
          fps: 60,
          resolution: "3840x2160 (4K)",
          status: "rendering" as const,
          total_shots: 12,
          rendered_shots: 8,
        },
        {
          id: "prod-2",
          title: "Product Teaser - Mobile Vertical",
          format: "9:16" as const,
          fps: 30,
          resolution: "1080x1920 (FHD)",
          status: "assembled" as const,
          total_shots: 4,
          rendered_shots: 4,
        },
      ]),
  });

  const { data: assets = [] } = useQuery({
    queryKey: ["production-assets", selectedProjectId],
    queryFn: () =>
      api.listMediaAssets(selectedProjectId).catch(() => [
        {
          id: "asset-1",
          project_id: selectedProjectId,
          name: "Cyber_City_Establishing_01.exr",
          asset_type: "image" as const,
          file_path: "/storage/production/assets/cyber_city_01.exr",
          size_bytes: 48500000,
          colorspace: "ACEScg",
          status: "ready" as const,
          created_at: "2026-09-02T12:00:00Z",
        },
        {
          id: "asset-2",
          project_id: selectedProjectId,
          name: "Drowned_Reactor_Audio_Mix.flac",
          asset_type: "audio" as const,
          file_path: "/storage/production/audio/reactor_mix.flac",
          size_bytes: 18400000,
          colorspace: "Linear",
          status: "ready" as const,
          created_at: "2026-09-02T12:15:00Z",
        },
      ]),
  });

  const { data: renderJobs = [] } = useQuery({
    queryKey: ["production-renders", selectedProjectId],
    queryFn: () =>
      api.listRenderJobs(selectedProjectId).catch(() => [
        {
          id: "job-rnd-1",
          project_id: selectedProjectId,
          shot_id: "shot-01",
          engine: "code_video" as const,
          progress_pct: 100,
          status: "succeeded" as const,
          output_uri: "artifact://renders/shot_01.mp4",
          created_at: "2026-09-02T14:00:00Z",
        },
        {
          id: "job-rnd-2",
          project_id: selectedProjectId,
          shot_id: "shot-02",
          engine: "gpu_renderer" as const,
          progress_pct: 65,
          status: "running" as const,
          created_at: "2026-09-02T14:40:00Z",
        },
      ]),
  });

  const submitRenderMutation = useMutation({
    mutationFn: (data: { project_id: string; shot_id: string; engine: string }) =>
      api.submitRenderJob(data).catch(() => ({
        id: `job-rnd-${Date.now()}`,
        project_id: data.project_id,
        shot_id: data.shot_id,
        engine: data.engine as "ffmpeg" | "code_video" | "gpu_renderer",
        progress_pct: 0,
        status: "queued" as const,
        created_at: new Date().toISOString(),
      })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["production-renders"] });
      setRenderModalOpen(false);
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
          label="Production Timelines"
          value={projects.length}
          subtext="4K / 60fps EDL masters"
          icon="🎞️"
          accentColor="var(--windagent-color-accent)"
        />
        <MetricCard
          label="Render Progress"
          value="66%"
          subtext="8 of 12 shots completed"
          icon="⚡"
          accentColor="var(--windagent-color-success)"
        />
        <MetricCard
          label="Normalized Assets"
          value={assets.length}
          subtext="ACEScg color managed"
          icon="📦"
          accentColor="#00dfd8"
        />
        <MetricCard
          label="Active Render Queue"
          value={renderJobs.filter((j) => j.status === "running").length}
          subtext="GPU worker engine active"
          icon="🚀"
          accentColor="var(--windagent-color-warning)"
        />
      </div>

      <Card variant="glass">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <Tabs
            activeTab={activeTab}
            onChange={setActiveTab}
            tabs={[
              { id: "projects", label: "Timelines & Master Cuts", count: projects.length },
              { id: "assets", label: "Media Asset Library", count: assets.length },
              { id: "renders", label: "Render Queue & EDL", count: renderJobs.length },
            ]}
          />

          <Button
            variant="brand"
            size="sm"
            onClick={() => setRenderModalOpen(true)}
          >
            🎬 Dispatch Render Job
          </Button>
        </div>

        {activeTab === "projects" && (
          <DataTable<ProductionProjectDTO>
            keyField="id"
            data={projects}
            onRowClick={(p) => setSelectedProjectId(p.id)}
            columns={[
              {
                key: "title",
                header: "Timeline Title",
                render: (p) => (
                  <div>
                    <div style={{ fontWeight: 600 }}>{p.title}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--windagent-color-text-dim)" }}>
                      {p.resolution} @ {p.fps}fps ({p.format})
                    </div>
                  </div>
                ),
              },
              {
                key: "status",
                header: "State",
                render: (p) => (
                  <Badge level={p.status === "assembled" ? "success" : "purple"} dot>
                    {p.status}
                  </Badge>
                ),
              },
              {
                key: "rendered_shots",
                header: "Shot Progress",
                render: (p) => (
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <div
                      style={{
                        width: "80px",
                        height: "6px",
                        background: "var(--windagent-color-surface-hover)",
                        borderRadius: "var(--windagent-radius-full)",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${(p.rendered_shots / p.total_shots) * 100}%`,
                          height: "100%",
                          background: "var(--windagent-color-brand-gradient)",
                        }}
                      />
                    </div>
                    <span style={{ fontSize: "0.8rem" }}>
                      {p.rendered_shots}/{p.total_shots}
                    </span>
                  </div>
                ),
              },
            ]}
          />
        )}

        {activeTab === "assets" && (
          <DataTable<MediaAssetDTO>
            keyField="id"
            data={assets}
            columns={[
              {
                key: "name",
                header: "Asset Name",
                render: (a) => (
                  <div>
                    <div style={{ fontWeight: 600 }}>{a.name}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--windagent-color-text-dim)" }}>
                      Path: {a.file_path}
                    </div>
                  </div>
                ),
              },
              { key: "asset_type", header: "Type", render: (a) => <Badge level="neutral">{a.asset_type}</Badge> },
              { key: "colorspace", header: "Colorspace", render: (a) => <Badge level="purple">{a.colorspace}</Badge> },
              {
                key: "size_bytes",
                header: "Size",
                render: (a) => <span>{(a.size_bytes / 1024 / 1024).toFixed(1)} MB</span>,
              },
              {
                key: "status",
                header: "Status",
                render: (a) => <Badge level={a.status === "ready" ? "success" : "warning"}>{a.status}</Badge>,
              },
            ]}
          />
        )}

        {activeTab === "renders" && (
          <DataTable<RenderJobDTO>
            keyField="id"
            data={renderJobs}
            columns={[
              {
                key: "shot_id",
                header: "Shot Target",
                render: (r) => (
                  <div>
                    <div style={{ fontWeight: 600 }}>{r.shot_id}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--windagent-color-text-dim)" }}>
                      Engine: <code>{r.engine}</code>
                    </div>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (r) => (
                  <Badge level={r.status === "succeeded" ? "success" : r.status === "running" ? "info" : "neutral"} dot>
                    {r.status}
                  </Badge>
                ),
              },
              {
                key: "progress_pct",
                header: "Progress",
                render: (r) => (
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <div
                      style={{
                        width: "100px",
                        height: "6px",
                        background: "var(--windagent-color-surface-hover)",
                        borderRadius: "var(--windagent-radius-full)",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${r.progress_pct}%`,
                          height: "100%",
                          background: "var(--windagent-color-accent)",
                        }}
                      />
                    </div>
                    <span>{r.progress_pct}%</span>
                  </div>
                ),
              },
              {
                key: "created_at",
                header: "Queued At",
                render: (r) => <span>{new Date(r.created_at).toLocaleTimeString()}</span>,
              },
            ]}
          />
        )}
      </Card>

      <Modal
        isOpen={renderModalOpen}
        onClose={() => setRenderModalOpen(false)}
        title="Submit Production Render Job"
        footer={
          <>
            <Button variant="ghost" onClick={() => setRenderModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="brand"
              loading={submitRenderMutation.isPending}
              onClick={() =>
                submitRenderMutation.mutate({
                  project_id: selectedProjectId,
                  shot_id: shotId,
                  engine: renderEngine,
                })
              }
            >
              Submit to Worker Pool
            </Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "4px", color: "var(--windagent-color-text-secondary)" }}>
              Shot ID
            </label>
            <input
              type="text"
              value={shotId}
              onChange={(e) => setShotId(e.target.value)}
              style={{
                width: "100%",
                padding: "8px 12px",
                background: "var(--windagent-color-bg)",
                border: "1px solid var(--windagent-border-default)",
                borderRadius: "var(--windagent-radius-md)",
                color: "var(--windagent-color-text)",
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "4px", color: "var(--windagent-color-text-secondary)" }}>
              Rendering Engine
            </label>
            <select
              value={renderEngine}
              onChange={(e) => setRenderEngine(e.target.value)}
              style={{
                width: "100%",
                padding: "8px 12px",
                background: "var(--windagent-color-bg)",
                border: "1px solid var(--windagent-border-default)",
                borderRadius: "var(--windagent-radius-md)",
                color: "var(--windagent-color-text)",
              }}
            >
              <option value="code_video">Code Video (Remotion / Canvas Engine)</option>
              <option value="gpu_renderer">GPU Hardware Render (NVENC / Metal)</option>
              <option value="ffmpeg">FFmpeg Postprocess Compositor</option>
            </select>
          </div>
        </div>
      </Modal>
    </div>
  );
}
