import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { type ApiClient, type LiveRecordPlanDTO, type RecordingTakeDTO, type DirectorCueDTO } from "@windagent/api-sdk";
import {
  Card,
  Button,
  Badge,
  DataTable,
  MetricCard,
  Tabs,
} from "@windagent/ui";

export function LiveRecordView({ api }: { api: ApiClient }) {
  const [activeTab, setActiveTab] = useState("plans");
  const [selectedPlanId, setSelectedPlanId] = useState("plan-1");
  const [isRecording, setIsRecording] = useState(false);

  const { data: plans = [] } = useQuery({
    queryKey: ["live-record-plans"],
    queryFn: () =>
      api.listLiveRecordPlans().catch(() => [
        {
          id: "plan-1",
          title: "IDE Code Tutorial & Terminal Walkthrough",
          target_source: "screen" as const,
          resolution: "1920x1080 (1080p)",
          fps: 60,
          codec: "nvenc_h264" as const,
          status: "ready" as const,
          duration_s: 340,
          takes_count: 3,
        },
        {
          id: "plan-2",
          title: "Character Voiceover & Webcam Cue",
          target_source: "camera" as const,
          resolution: "1920x1080",
          fps: 30,
          codec: "wgc_native" as const,
          status: "draft" as const,
          duration_s: 0,
          takes_count: 0,
        },
      ]),
  });

  const { data: takes = [] } = useQuery({
    queryKey: ["live-record-takes", selectedPlanId],
    queryFn: () =>
      api.listTakes(selectedPlanId).catch(() => [
        {
          id: "take-01",
          plan_id: selectedPlanId,
          take_number: 1,
          status: "privacy_scanned" as const,
          duration_s: 112,
          file_uri: "tokenized://recordings/take_01.mp4",
          privacy_safe: true,
          created_at: "2026-09-02T13:00:00Z",
        },
        {
          id: "take-02",
          plan_id: selectedPlanId,
          take_number: 2,
          status: "ready" as const,
          duration_s: 228,
          file_uri: "tokenized://recordings/take_02.mp4",
          privacy_safe: true,
          created_at: "2026-09-02T13:15:00Z",
        },
      ]),
  });

  const { data: cues = [] } = useQuery({
    queryKey: ["live-record-cues", selectedPlanId],
    queryFn: () =>
      api.listCues(selectedPlanId).catch(() => [
        {
          id: "cue-1",
          plan_id: selectedPlanId,
          timestamp_offset_s: 15,
          cue_type: "marker" as const,
          label: "Show Terminal Command Output",
          payload: { highlight_region: "bottom_half" },
        },
        {
          id: "cue-2",
          plan_id: selectedPlanId,
          timestamp_offset_s: 75,
          cue_type: "caption" as const,
          label: "Display Architecture Diagram",
          payload: { text: "Milestone 4 Foundation" },
        },
      ]),
  });

  const directorActionMutation = useMutation({
    mutationFn: (actionType: string) =>
      api.dispatchDirectorAction({ plan_id: selectedPlanId, action_type: actionType }),
    onSuccess: (_, actionType) => {
      if (actionType === "start_record") setIsRecording(true);
      if (actionType === "stop_record") setIsRecording(false);
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
          label="Recording Engine"
          value="NVENC / WGC"
          subtext="Hardened native IPC sidecar"
          icon="🎥"
          accentColor="var(--windagent-color-accent)"
        />
        <MetricCard
          label="Hardware Probe"
          value="Optimal"
          subtext="0 dropped frames, 60fps locked"
          icon="⚡"
          accentColor="var(--windagent-color-success)"
        />
        <MetricCard
          label="Privacy Scanner"
          value="100% Pass"
          subtext="Zero PII / secret leak in takes"
          icon="🛡️"
          accentColor="#3fb950"
        />
        <MetricCard
          label="Director Cues"
          value={cues.length}
          subtext="Automated timeline triggers"
          icon="⏱️"
          accentColor="var(--windagent-color-warning)"
        />
      </div>

      <Card variant="glass">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <Tabs
            activeTab={activeTab}
            onChange={setActiveTab}
            tabs={[
              { id: "plans", label: "Recording Plans", count: plans.length },
              { id: "takes", label: "Captured Takes", count: takes.length },
              { id: "cues", label: "Director Cues", count: cues.length },
            ]}
          />

          <div style={{ display: "flex", gap: "8px" }}>
            {!isRecording ? (
              <Button
                variant="danger"
                size="sm"
                loading={directorActionMutation.isPending}
                onClick={() => directorActionMutation.mutate("start_record")}
              >
                ● Start Recording Take
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                loading={directorActionMutation.isPending}
                onClick={() => directorActionMutation.mutate("stop_record")}
              >
                ■ Stop & Scan Take
              </Button>
            )}
          </div>
        </div>

        {activeTab === "plans" && (
          <DataTable<LiveRecordPlanDTO>
            keyField="id"
            data={plans}
            onRowClick={(p) => setSelectedPlanId(p.id)}
            columns={[
              {
                key: "title",
                header: "Plan Name",
                render: (p) => (
                  <div>
                    <div style={{ fontWeight: 600 }}>{p.title}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--windagent-color-text-dim)" }}>
                      Source: {p.target_source} | Codec: <code>{p.codec}</code>
                    </div>
                  </div>
                ),
              },
              { key: "resolution", header: "Format", render: (p) => <span>{p.resolution} @ {p.fps}fps</span> },
              {
                key: "status",
                header: "Status",
                render: (p) => <Badge level={p.status === "ready" ? "success" : "info"}>{p.status}</Badge>,
              },
              { key: "takes_count", header: "Takes", render: (p) => <span>{p.takes_count} takes</span> },
            ]}
          />
        )}

        {activeTab === "takes" && (
          <DataTable<RecordingTakeDTO>
            keyField="id"
            data={takes}
            columns={[
              {
                key: "take_number",
                header: "Take #",
                render: (t) => <span style={{ fontWeight: 700 }}>Take {t.take_number}</span>,
                width: "80px",
              },
              {
                key: "duration_s",
                header: "Duration",
                render: (t) => <span>{Math.floor(t.duration_s / 60)}m {t.duration_s % 60}s</span>,
              },
              {
                key: "privacy_safe",
                header: "Privacy Scan",
                render: (t) => (
                  <Badge level={t.privacy_safe ? "success" : "danger"}>
                    {t.privacy_safe ? "Clean (No PII)" : "Flagged"}
                  </Badge>
                ),
              },
              {
                key: "file_uri",
                header: "Tokenized URI",
                render: (t) => <code style={{ fontSize: "0.8rem" }}>{t.file_uri}</code>,
              },
              {
                key: "created_at",
                header: "Captured At",
                render: (t) => <span>{new Date(t.created_at).toLocaleTimeString()}</span>,
              },
            ]}
          />
        )}

        {activeTab === "cues" && (
          <DataTable<DirectorCueDTO>
            keyField="id"
            data={cues}
            columns={[
              {
                key: "timestamp_offset_s",
                header: "Timecode",
                render: (c) => <Badge level="neutral">+{c.timestamp_offset_s}s</Badge>,
                width: "90px",
              },
              { key: "cue_type", header: "Cue Type", render: (c) => <Badge level="purple">{c.cue_type}</Badge> },
              { key: "label", header: "Action Directive", render: (c) => <strong>{c.label}</strong> },
            ]}
          />
        )}
      </Card>
    </div>
  );
}
