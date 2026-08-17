/**
 * EpisodePipeline — Interactive stepper showing pipeline stages and progress.
 */

import React from 'react';
import { CheckCircle2, Lock } from 'lucide-react';
import { CHECKPOINT_STEPS, type CheckpointStage } from '../model/types';

export interface EpisodePipelineProps {
  currentCheckpoint: string;
  state: string;
  activeTab: string;
  onSelectTab: (stage: CheckpointStage) => void;
}

export const EpisodePipeline: React.FC<EpisodePipelineProps> = ({
  currentCheckpoint,
  state,
  activeTab,
  onSelectTab,
}) => {
  const currentStep = CHECKPOINT_STEPS.find((s) => s.id === currentCheckpoint);
  const currentOrder = currentStep?.order ?? 1;
  const isLocked = state === 'LOCKED' || state === 'READY_FOR_PRODUCTION';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        background: 'var(--bg-panel, #0f172a)',
        borderRadius: '16px',
        padding: '12px 20px',
        border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
        gap: '8px',
        overflowX: 'auto',
        marginBottom: '24px',
      }}
      data-testid="episode-pipeline-stepper"
    >
      {CHECKPOINT_STEPS.map((step, idx) => {
        const isPassed = isLocked || step.order < currentOrder;
        const isCurrent = !isLocked && step.order === currentOrder;
        const isSelected = activeTab === step.id;

        let statusBg = 'rgba(255, 255, 255, 0.05)';
        if (isPassed) {
          statusBg = 'rgba(34, 197, 94, 0.12)';
        } else if (isCurrent) {
          statusBg = 'rgba(56, 189, 248, 0.15)';
        }


        return (
          <React.Fragment key={step.id}>
            <button
              onClick={() => onSelectTab(step.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '8px 14px',
                borderRadius: '10px',
                background: isSelected ? 'rgba(59, 130, 246, 0.18)' : statusBg,
                border: isSelected
                  ? '1px solid var(--color-primary, #3b82f6)'
                  : `1px solid ${isCurrent ? '#38bdf8' : 'rgba(255, 255, 255, 0.06)'}`,
                cursor: 'pointer',
                transition: 'all 0.2s',
                whiteSpace: 'nowrap',
              }}
            >
              <div
                style={{
                  width: '24px',
                  height: '24px',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: isPassed ? '#22c55e' : isCurrent ? '#0284c7' : 'rgba(255, 255, 255, 0.1)',
                  color: '#ffffff',
                  fontSize: '11px',
                  fontWeight: 700,
                }}
              >
                {isPassed ? <CheckCircle2 size={14} /> : isLocked && step.id === 'LOCKED' ? <Lock size={12} /> : step.order}
              </div>

              <div style={{ textAlign: 'left' }}>
                <span
                  style={{
                    display: 'block',
                    fontSize: '13px',
                    fontWeight: isSelected ? 700 : 600,
                    color: isSelected ? '#ffffff' : isCurrent ? '#38bdf8' : isPassed ? '#f8fafc' : '#94a3b8',
                  }}
                >
                  {step.shortLabel}
                </span>
              </div>
            </button>

            {idx < CHECKPOINT_STEPS.length - 1 && (
              <div
                style={{
                  width: '20px',
                  height: '2px',
                  background: isPassed ? '#22c55e' : 'rgba(255, 255, 255, 0.1)',
                  flexShrink: 0,
                }}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};
