import React, { useState } from 'react';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';

import { PipelineProgress } from '../runtime/PipelineProgress';
import { ArtifactContentView } from '../shared/ArtifactView';
import { ScreenplayDiffView, type ScreenplayDraftContent } from '../screenplay/ScreenplayView';
import { StoryTabContainer } from '../story/StoryBibleView';

export type EpisodeTab =
  | 'overview'
  | 'idea'
  | 'story'
  | 'outline'
  | 'screenplay'
  | 'review'
  | 'revisions'
  | 'activity';

export interface EpisodeWorkspaceProps {
  episode: Record<string, unknown>;
  artifacts: StudioArtifactEnvelope[];
  busy?: boolean;
  onSelectIdea?: (candidateId: string, envelope: StudioArtifactEnvelope) => void;
  renderRunProgress?: () => React.ReactNode;
  renderApprovalBar?: () => React.ReactNode;
  renderActions?: () => React.ReactNode;
}

const TABS: Array<{ id: EpisodeTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'idea', label: 'Idea' },
  { id: 'story', label: 'Story' },
  { id: 'outline', label: 'Outline' },
  { id: 'screenplay', label: 'Screenplay' },
  { id: 'review', label: 'Review' },
  { id: 'revisions', label: 'Revisions' },
  { id: 'activity', label: 'Activity' },
];

export function EpisodeWorkspace({
  episode,
  artifacts,
  busy,
  onSelectIdea,
  renderRunProgress,
  renderApprovalBar,
  renderActions,
}: EpisodeWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<EpisodeTab>('overview');

  const state = String(episode.state ?? 'DRAFT');

  // Filter artifacts by section
  const ideaArtifacts = artifacts.filter((a) =>
    ['IdeaCandidateSet', 'SelectedIdea'].includes(a.artifact_type)
  );

  const storyArtifacts = artifacts.filter((a) =>
    ['StoryBible', 'WorldBible', 'CharacterCanon', 'BeatSheet'].includes(a.artifact_type)
  );

  const outlineArtifacts = artifacts.filter((a) =>
    ['EpisodeOutline'].includes(a.artifact_type)
  );

  const screenplayArtifacts = artifacts.filter((a) =>
    ['ScreenplayDraft'].includes(a.artifact_type)
  );

  const reviewArtifacts = artifacts.filter((a) =>
    ['ReviewReport'].includes(a.artifact_type)
  );

  const revisionArtifacts = artifacts.filter((a) =>
    ['RevisionProposal', 'LockedScreenplayReceipt', 'LockedScreenplayPackage'].includes(
      a.artifact_type
    )
  );

  const screenplayDrafts = artifacts
    .filter((a) => a.artifact_type === 'ScreenplayDraft')
    .sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Stepper progress */}
      <PipelineProgress currentState={state} />

      {/* Tab bar */}
      <div
        role="tablist"
        style={{
          display: 'flex',
          gap: 4,
          borderBottom: '1px solid var(--studio-border, #334155)',
          paddingBottom: 2,
        }}
      >
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={active}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: '8px 16px',
                border: 'none',
                background: 'transparent',
                borderBottom: active ? '2px solid #7dd3fc' : '2px solid transparent',
                color: active ? '#7dd3fc' : '#94a3b8',
                fontWeight: active ? 600 : 400,
                cursor: 'pointer',
                fontSize: 14,
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab Panels */}
      {activeTab === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {renderActions?.()}
          {renderRunProgress?.()}
          {renderApprovalBar?.()}

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: 16,
            }}
          >
            <div
              style={{
                padding: 16,
                border: '1px solid var(--studio-border, #334155)',
                borderRadius: 8,
                background: 'var(--studio-surface-2, #1e293b)',
              }}
            >
              <h4 style={{ margin: '0 0 8px', fontSize: 14, color: '#94a3b8' }}>
                Episode Status Summary
              </h4>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0' }}>{state}</div>
              <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
                Optimistic Version: {String(episode.optimistic_version ?? episode.version ?? 0)}
              </div>
            </div>

            <div
              style={{
                padding: 16,
                border: '1px solid var(--studio-border, #334155)',
                borderRadius: 8,
                background: 'var(--studio-surface-2, #1e293b)',
              }}
            >
              <h4 style={{ margin: '0 0 8px', fontSize: 14, color: '#94a3b8' }}>
                Artifact Lineage
              </h4>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#7dd3fc' }}>
                {artifacts.length} Artifacts
              </div>
              <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
                Latest: {artifacts[artifacts.length - 1]?.artifact_type ?? 'None'}
              </div>
            </div>
          </div>

          <h4 style={{ margin: '8px 0 0' }}>Artifact Lineage &amp; Content</h4>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {artifacts.length === 0 && !busy && <div style={{ color: '#94a3b8' }}>No artifacts yet.</div>}
            {screenplayDrafts.length >= 2 && (
              <div style={{ border: '1px solid #1e293b', borderRadius: 8, padding: 10 }}>
                <ScreenplayDiffView
                  before={screenplayDrafts[1].content as unknown as ScreenplayDraftContent}
                  after={screenplayDrafts[0].content as unknown as ScreenplayDraftContent}
                />
              </div>
            )}
            {artifacts.map((a) => (
              <div key={a.artifact_id} style={{ border: '1px solid #1e293b', borderRadius: 8, padding: 10 }}>
                {a.artifact_type === 'IdeaCandidateSet' ? (
                  <ArtifactContentView
                    artifact={a}
                    onSelectIdea={(candidateId) => onSelectIdea?.(candidateId, a)}
                    selectDisabled={busy}
                    isLocked={['SCREENPLAY_LOCKED', 'READY_FOR_PRODUCTION'].includes(state)}
                  />
                ) : (
                  <ArtifactContentView artifact={a} isLocked={['SCREENPLAY_LOCKED', 'READY_FOR_PRODUCTION'].includes(state)} />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'idea' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {ideaArtifacts.length === 0 && <div style={{ color: '#94a3b8' }}>No idea artifacts yet.</div>}
          {ideaArtifacts.map((a) => (
            <div key={a.artifact_id} style={{ border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
              <ArtifactContentView
                artifact={a}
                onSelectIdea={(candidateId) => onSelectIdea?.(candidateId, a)}
                selectDisabled={busy}
              />
            </div>
          ))}
        </div>
      )}

      {activeTab === 'story' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {storyArtifacts.length === 0 ? (
            <div style={{ color: '#94a3b8' }}>No story artifacts yet.</div>
          ) : (
            <StoryTabContainer artifacts={storyArtifacts} />
          )}
        </div>
      )}

      {activeTab === 'outline' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {outlineArtifacts.length === 0 && <div style={{ color: '#94a3b8' }}>No outline artifacts yet.</div>}
          {outlineArtifacts.map((a) => (
            <div key={a.artifact_id} style={{ border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
              <ArtifactContentView artifact={a} />
            </div>
          ))}
        </div>
      )}

      {activeTab === 'screenplay' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {screenplayDrafts.length >= 2 && (
            <div style={{ border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
              <ScreenplayDiffView
                before={screenplayDrafts[1].content as unknown as ScreenplayDraftContent}
                after={screenplayDrafts[0].content as unknown as ScreenplayDraftContent}
              />
            </div>
          )}
          {screenplayArtifacts.length === 0 && <div style={{ color: '#94a3b8' }}>No screenplay drafts yet.</div>}
          {screenplayArtifacts.map((a) => (
            <div key={a.artifact_id} style={{ border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
              <ArtifactContentView artifact={a} />
            </div>
          ))}
        </div>
      )}

      {activeTab === 'review' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {reviewArtifacts.length === 0 && <div style={{ color: '#94a3b8' }}>No review reports yet.</div>}
          {reviewArtifacts.map((a) => (
            <div key={a.artifact_id} style={{ border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
              <ArtifactContentView artifact={a} />
            </div>
          ))}
        </div>
      )}

      {activeTab === 'revisions' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {revisionArtifacts.length === 0 && <div style={{ color: '#94a3b8' }}>No revision or lock receipts yet.</div>}
          {revisionArtifacts.map((a) => (
            <div key={a.artifact_id} style={{ border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
              <ArtifactContentView artifact={a} />
            </div>
          ))}
        </div>
      )}

      {activeTab === 'activity' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, padding: 14 }}>
            <h4 style={{ margin: '0 0 12px', fontSize: 15, color: '#e2e8f0' }}>Server Milestone Events</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#4ade80' }}>
                <span style={{ background: '#14532d', color: '#4ade80', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600 }}>✓ Event</span>
                <b>Idea generation started</b>
              </div>
              {artifacts.some((a) => a.artifact_type === 'IdeaCandidateSet') && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#4ade80' }}>
                  <span style={{ background: '#14532d', color: '#4ade80', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600 }}>✓ Event</span>
                  <b>Idea candidates generated</b>
                </div>
              )}
              {artifacts.some((a) => a.artifact_type === 'SelectedIdea') && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#4ade80' }}>
                  <span style={{ background: '#14532d', color: '#4ade80', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600 }}>✓ Event</span>
                  <b>Idea selected</b>
                </div>
              )}
              {artifacts.some((a) => ['StoryBible', 'BeatSheet'].includes(a.artifact_type)) && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#4ade80' }}>
                  <span style={{ background: '#14532d', color: '#4ade80', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600 }}>✓ Event</span>
                  <b>Story development completed</b>
                </div>
              )}
              {artifacts.some((a) => a.artifact_type === 'ReviewReport') && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#4ade80' }}>
                  <span style={{ background: '#14532d', color: '#4ade80', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600 }}>✓ Event</span>
                  <b>Review completed</b>
                </div>
              )}
              {artifacts.some((a) => a.artifact_type === 'RevisionProposal') && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#4ade80' }}>
                  <span style={{ background: '#14532d', color: '#4ade80', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600 }}>✓ Event</span>
                  <b>Revision created</b>
                </div>
              )}
              {artifacts.some((a) => ['LockedScreenplayReceipt', 'LockedScreenplayPackage'].includes(a.artifact_type)) && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#4ade80' }}>
                  <span style={{ background: '#14532d', color: '#4ade80', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600 }}>✓ Event</span>
                  <b>Screenplay locked</b>
                </div>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <h4 style={{ margin: 0 }}>Artifact Timeline</h4>
            {artifacts.length === 0 && <div style={{ color: '#94a3b8' }}>No activity yet.</div>}
            {artifacts.map((a) => (
              <div key={a.artifact_id} style={{ border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
                <ArtifactContentView artifact={a} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
