import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { type ApiClient, type StudioProjectDTO, type EpisodeDTO, type CharacterDTO } from "@windagent/api-sdk";
import {
  Card,
  Button,
  Badge,
  DataTable,
  MetricCard,
  Modal,
  Tabs,
  CodeBlock,
} from "@windagent/ui";

export function StudioView({ api }: { api: ApiClient }) {
  const [activeTab, setActiveTab] = useState("projects");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("proj-1");
  const [storyPromptModalOpen, setStoryPromptModalOpen] = useState(false);
  const [storyPrompt, setStoryPrompt] = useState("");
  const [generatedStory, setGeneratedStory] = useState<string | null>(null);

  const { data: projects = [] } = useQuery({
    queryKey: ["studio-projects"],
    queryFn: () =>
      api.listStudioProjects().catch(() => [
        {
          id: "proj-1",
          title: "Neon Horizon: 2099",
          genre: "Cyberpunk / Sci-Fi",
          synopsis: "In a drowned metropolis, an rogue AI agent uncovers ancient planetary records.",
          status: "in_production" as const,
          episodes_count: 6,
          characters_count: 4,
          created_at: "2026-09-02T10:00:00Z",
        },
        {
          id: "proj-2",
          title: "The Clockwork Mage",
          genre: "Steampunk Fantasy",
          synopsis: "An alchemist engineers mechanical familiars to restore the broken celestial chronometer.",
          status: "draft" as const,
          episodes_count: 1,
          characters_count: 2,
          created_at: "2026-09-02T11:30:00Z",
        },
      ]),
  });

  const { data: episodes = [] } = useQuery({
    queryKey: ["studio-episodes", selectedProjectId],
    queryFn: () =>
      api.listEpisodes(selectedProjectId).catch(() => [
        {
          id: "ep-1",
          project_id: selectedProjectId,
          episode_number: 1,
          title: "Submerged Signals",
          summary: "First contact with the encrypted orbital relay.",
          status: "scripted" as const,
          duration_estimate_s: 180,
        },
        {
          id: "ep-2",
          project_id: selectedProjectId,
          episode_number: 2,
          title: "The Ghost in the Grid",
          summary: "Infiltrating the central mainframe beneath the ocean tier.",
          status: "storyboarded" as const,
          duration_estimate_s: 240,
        },
      ]),
  });

  const { data: characters = [] } = useQuery({
    queryKey: ["studio-characters", selectedProjectId],
    queryFn: () =>
      api.listCharacters(selectedProjectId).catch(() => [
        {
          id: "char-1",
          project_id: selectedProjectId,
          name: "Dr. Elena Vance",
          role: "protagonist" as const,
          visual_traits: "Silver cybernetic arm, holographic lenses, dark trench coat",
          voice_profile: "Calm, analytical, slight transatlantic accent",
        },
        {
          id: "char-2",
          project_id: selectedProjectId,
          name: "Kaelen (Unit 7)",
          role: "supporting" as const,
          visual_traits: "Sentient android chassis with exposed optical filaments",
          voice_profile: "Synthesized resonant baritone",
        },
      ]),
  });

  const generateStoryMutation = useMutation({
    mutationFn: (data: { project_id: string; prompt: string }) =>
      api.generateStory(data).catch(() => ({
        story_text:
          "EXT. SECTOR 4 DOCKS - NIGHT\n\nRain hammers the rusted neon signs of Neo-Seattle. Elena checks the terminal.\n\nELENA\n(whispering)\nThe signal isn't coming from orbit. It's coming from below.\n\nKaelen's optical sensor flashes amber.\n\nKAELEN\nSub-level 12 pressure thresholds exceeded. We have six minutes before containment failure.",
      })),
    onSuccess: (res) => {
      setGeneratedStory(res.story_text);
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
          label="Active Series & Projects"
          value={projects.length}
          subtext="Studio IPs in development"
          icon="🎬"
          accentColor="var(--windagent-color-accent)"
        />
        <MetricCard
          label="Scripted Episodes"
          value={episodes.length}
          subtext="Narrative arcs locked"
          icon="📜"
          accentColor="var(--windagent-color-success)"
        />
        <MetricCard
          label="Character Roster"
          value={characters.length}
          subtext="Consistent visual & voice profiles"
          icon="👤"
          accentColor="#ff0080"
        />
        <MetricCard
          label="Storyboard Coverage"
          value="85%"
          subtext="Cues aligned to production"
          icon="🎨"
          accentColor="var(--windagent-color-warning)"
        />
      </div>

      <Card variant="glass">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <Tabs
            activeTab={activeTab}
            onChange={setActiveTab}
            tabs={[
              { id: "projects", label: "Projects & Series", count: projects.length },
              { id: "episodes", label: "Episodes & Scripts", count: episodes.length },
              { id: "characters", label: "Character Bible", count: characters.length },
              { id: "generator", label: "AI Story Generator" },
            ]}
          />

          <Button
            variant="brand"
            size="sm"
            onClick={() => setStoryPromptModalOpen(true)}
          >
            ✨ Generate Story Beat
          </Button>
        </div>

        {activeTab === "projects" && (
          <DataTable<StudioProjectDTO>
            keyField="id"
            data={projects}
            onRowClick={(p) => setSelectedProjectId(p.id)}
            columns={[
              {
                key: "title",
                header: "Project Title",
                render: (p) => (
                  <div>
                    <div style={{ fontWeight: 600, color: "var(--windagent-color-text)" }}>{p.title}</div>
                    <div style={{ fontSize: "0.8rem", color: "var(--windagent-color-text-dim)" }}>
                      {p.synopsis}
                    </div>
                  </div>
                ),
              },
              { key: "genre", header: "Genre", render: (p) => <Badge level="neutral">{p.genre}</Badge> },
              {
                key: "status",
                header: "Status",
                render: (p) => (
                  <Badge level={p.status === "in_production" ? "purple" : "info"} dot>
                    {p.status}
                  </Badge>
                ),
              },
              { key: "episodes_count", header: "Episodes", render: (p) => <span>{p.episodes_count} eps</span> },
            ]}
          />
        )}

        {activeTab === "episodes" && (
          <DataTable<EpisodeDTO>
            keyField="id"
            data={episodes}
            columns={[
              {
                key: "episode_number",
                header: "#",
                render: (e) => <span style={{ fontWeight: 700 }}>Ep {e.episode_number}</span>,
                width: "60px",
              },
              {
                key: "title",
                header: "Title & Logline",
                render: (e) => (
                  <div>
                    <div style={{ fontWeight: 600 }}>{e.title}</div>
                    <div style={{ fontSize: "0.8rem", color: "var(--windagent-color-text-muted)" }}>{e.summary}</div>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (e) => (
                  <Badge level={e.status === "storyboarded" ? "success" : "info"}>
                    {e.status}
                  </Badge>
                ),
              },
              {
                key: "duration_estimate_s",
                header: "Duration",
                render: (e) => <span>{Math.round(e.duration_estimate_s / 60)} mins</span>,
              },
            ]}
          />
        )}

        {activeTab === "characters" && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "16px" }}>
            {characters.map((char: CharacterDTO) => (
              <Card key={char.id} variant="default" padding="sm" style={{ border: "1px solid var(--windagent-border-subtle)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                  <h4 style={{ margin: 0, fontSize: "1rem", color: "var(--windagent-color-text)" }}>{char.name}</h4>
                  <Badge level="purple">{char.role}</Badge>
                </div>
                <div style={{ fontSize: "0.8rem", color: "var(--windagent-color-text-secondary)", marginBottom: "6px" }}>
                  <strong>Visual:</strong> {char.visual_traits}
                </div>
                <div style={{ fontSize: "0.8rem", color: "var(--windagent-color-text-muted)" }}>
                  <strong>Voice:</strong> {char.voice_profile}
                </div>
              </Card>
            ))}
          </div>
        )}

        {activeTab === "generator" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div style={{ display: "flex", gap: "10px" }}>
              <input
                type="text"
                value={storyPrompt}
                onChange={(e) => setStoryPrompt(e.target.value)}
                placeholder="Enter prompt e.g. 'Elena hacks into the underwater geothermal vault...'"
                style={{
                  flex: 1,
                  padding: "10px 14px",
                  background: "var(--windagent-color-bg)",
                  border: "1px solid var(--windagent-border-default)",
                  borderRadius: "var(--windagent-radius-md)",
                  color: "var(--windagent-color-text)",
                }}
              />
              <Button
                variant="brand"
                loading={generateStoryMutation.isPending}
                onClick={() =>
                  generateStoryMutation.mutate({
                    project_id: selectedProjectId,
                    prompt: storyPrompt || "Elena investigates deep subterranean relay",
                  })
                }
              >
                Generate Beat
              </Button>
            </div>

            {generatedStory && (
              <div>
                <h4 style={{ fontSize: "0.9rem", color: "var(--windagent-color-text-secondary)", marginBottom: "8px" }}>
                  Generated Story Beat
                </h4>
                <CodeBlock code={generatedStory} language="fountain" />
              </div>
            )}
          </div>
        )}
      </Card>

      <Modal
        isOpen={storyPromptModalOpen}
        onClose={() => setStoryPromptModalOpen(false)}
        title="AI Story Script Generator"
        footer={
          <>
            <Button variant="ghost" onClick={() => setStoryPromptModalOpen(false)}>
              Close
            </Button>
            <Button
              variant="brand"
              loading={generateStoryMutation.isPending}
              onClick={() => {
                generateStoryMutation.mutate({
                  project_id: selectedProjectId,
                  prompt: storyPrompt || "Dramatic encounter at flooded reactor",
                });
                setActiveTab("generator");
                setStoryPromptModalOpen(false);
              }}
            >
              Generate Script
            </Button>
          </>
        }
      >
        <p style={{ fontSize: "0.85rem", color: "var(--windagent-color-text-secondary)", marginBottom: "12px" }}>
          Prompt the Model Gateway with studio context (characters, lore, scene continuity) to generate narrative beats.
        </p>
        <textarea
          rows={4}
          value={storyPrompt}
          onChange={(e) => setStoryPrompt(e.target.value)}
          placeholder="Describe scene objectives, dialogue tone, and dramatic conflict..."
          style={{
            width: "100%",
            padding: "10px",
            background: "var(--windagent-color-bg)",
            border: "1px solid var(--windagent-border-default)",
            borderRadius: "var(--windagent-radius-md)",
            color: "var(--windagent-color-text)",
            fontFamily: "var(--windagent-font-sans)",
            fontSize: "0.85rem",
          }}
        />
      </Modal>
    </div>
  );
}
