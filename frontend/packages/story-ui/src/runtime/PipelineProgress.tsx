import React from 'react';

export interface PipelineProgressProps {
  currentState: string;
}

interface Stage {
  key: string;
  label: string;
}

const STAGES: Stage[] = [
  { key: 'idea', label: 'Idea' },
  { key: 'story', label: 'Story' },
  { key: 'outline', label: 'Outline' },
  { key: 'screenplay', label: 'Screenplay' },
  { key: 'review', label: 'Review' },
  { key: 'approval', label: 'Approval' },
  { key: 'locked', label: 'Locked' },
];

function getStageIndex(state: string): number {
  const normalized = state.toUpperCase();
  switch (normalized) {
    case 'IDEATION':
      return 0;
    case 'STORY_DEVELOPMENT':
      return 1;
    case 'OUTLINE_READY':
      return 2;
    case 'SCREENPLAY_DRAFT':
      return 3;
    case 'SCREENPLAY_REVIEW':
      return 4;
    case 'SCREENPLAY_APPROVAL':
    case 'AWAITING_APPROVAL':
      return 5;
    case 'SCREENPLAY_LOCKED':
    case 'LOCKED':
    case 'READY_FOR_PRODUCTION':
      return 6;
    default:
      return 0;
  }
}

export function PipelineProgress({ currentState }: PipelineProgressProps) {
  const activeIndex = getStageIndex(currentState);

  return (
    <nav
      aria-label="Pipeline progress"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
        padding: '12px 16px',
        background: 'var(--studio-surface-1, #1e293b)',
        border: '1px solid var(--studio-border, #334155)',
        borderRadius: 8,
        margin: '12px 0 20px',
        overflowX: 'auto',
      }}
    >
      {STAGES.map((stage, idx) => {
        const isCompleted = idx < activeIndex;
        const isActive = idx === activeIndex;

        let circleBg = 'var(--studio-surface-3, #475569)';
        let circleColor = '#94a3b8';
        let labelColor = '#94a3b8';

        if (isCompleted) {
          circleBg = '#4ade80';
          circleColor = '#0f172a';
          labelColor = '#e2e8f0';
        } else if (isActive) {
          circleBg = '#7dd3fc';
          circleColor = '#0f172a';
          labelColor = '#7dd3fc';
        }

        return (
          <React.Fragment key={stage.key}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  background: circleBg,
                  color: circleColor,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                {isCompleted ? '✓' : idx + 1}
              </div>
              <span style={{ fontSize: 13, fontWeight: isActive ? 600 : 400, color: labelColor }}>
                {stage.label}
              </span>
            </div>
            {idx < STAGES.length - 1 && (
              <div
                style={{
                  flex: 1,
                  height: 2,
                  minWidth: 16,
                  background: idx < activeIndex ? '#4ade80' : 'var(--studio-border, #334155)',
                }}
              />
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
}
