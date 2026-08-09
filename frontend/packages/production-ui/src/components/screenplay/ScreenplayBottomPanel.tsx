import React, { useState } from 'react';
import {
  ScreenplayDiffResultDTO,
  ScreenplayChangeImpactDTO,
  ScriptRevisionProposalDTO,
  ScreenplayValidationReportDTO,
} from '@windagent/production-contracts';
import { ScreenplayDiffView } from './ScreenplayDiffView';
import { ProductionImpactView } from './ProductionImpactView';
import { AIProposalView } from './AIProposalView';
import { ValidationGatePanel } from './ValidationGatePanel';

interface ScreenplayBottomPanelProps {
  diffResult: ScreenplayDiffResultDTO | null;
  impact: ScreenplayChangeImpactDTO | null;
  activeProposal: ScriptRevisionProposalDTO | null;
  validationReport: ScreenplayValidationReportDTO | null;
  onRequestProposal: (actionType: string, instruction: string) => void;
  onApproveProposal: (proposalId: string) => void;
  onRejectProposal: (proposalId: string) => void;
  onLockRevision: () => void;
  onSelectEntity?: (entityId: string) => void;
}

export const ScreenplayBottomPanel: React.FC<ScreenplayBottomPanelProps> = ({
  diffResult,
  impact,
  activeProposal,
  validationReport,
  onRequestProposal,
  onApproveProposal,
  onRejectProposal,
  onLockRevision,
  onSelectEntity,
}) => {
  const [activeTab, setActiveTab] = useState<'PROPOSAL' | 'DIFF' | 'IMPACT' | 'VALIDATION'>('VALIDATION');
  const blockingCount = validationReport?.blocking_count ?? 0;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '240px',
        backgroundColor: '#11111B',
        borderTop: '1px solid #313244',
        color: '#CDD6F4',
        fontFamily: 'Inter, system-ui, sans-serif',
      }}
    >
      {/* Bottom Panel Tab Header */}
      <div
        style={{
          display: 'flex',
          backgroundColor: '#181825',
          borderBottom: '1px solid #313244',
          padding: '0 0.5rem',
        }}
      >
        <button
          onClick={() => setActiveTab('VALIDATION')}
          style={{
            padding: '0.45rem 1rem',
            border: 'none',
            backgroundColor: activeTab === 'VALIDATION' ? '#1E1E2E' : 'transparent',
            color: activeTab === 'VALIDATION' ? '#F5E0DC' : '#A6ADC8',
            fontWeight: 700,
            fontSize: '0.75rem',
            cursor: 'pointer',
            borderBottom: activeTab === 'VALIDATION' ? '3px solid #89B4FA' : '3px solid transparent',
          }}
        >
          Validation Gate {blockingCount > 0 ? `(🔴 ${blockingCount})` : '(🟢 Pass)'}
        </button>
        <button
          onClick={() => setActiveTab('PROPOSAL')}
          style={{
            padding: '0.45rem 1rem',
            border: 'none',
            backgroundColor: activeTab === 'PROPOSAL' ? '#1E1E2E' : 'transparent',
            color: activeTab === 'PROPOSAL' ? '#F5E0DC' : '#A6ADC8',
            fontWeight: 700,
            fontSize: '0.75rem',
            cursor: 'pointer',
            borderBottom: activeTab === 'PROPOSAL' ? '3px solid #CBA6F7' : '3px solid transparent',
          }}
        >
          AI Assist
        </button>
        <button
          onClick={() => setActiveTab('DIFF')}
          style={{
            padding: '0.45rem 1rem',
            border: 'none',
            backgroundColor: activeTab === 'DIFF' ? '#1E1E2E' : 'transparent',
            color: activeTab === 'DIFF' ? '#F5E0DC' : '#A6ADC8',
            fontWeight: 700,
            fontSize: '0.75rem',
            cursor: 'pointer',
            borderBottom: activeTab === 'DIFF' ? '3px solid #FAB387' : '3px solid transparent',
          }}
        >
          Revision Diff
        </button>
        <button
          onClick={() => setActiveTab('IMPACT')}
          style={{
            padding: '0.45rem 1rem',
            border: 'none',
            backgroundColor: activeTab === 'IMPACT' ? '#1E1E2E' : 'transparent',
            color: activeTab === 'IMPACT' ? '#F5E0DC' : '#A6ADC8',
            fontWeight: 700,
            fontSize: '0.75rem',
            cursor: 'pointer',
            borderBottom: activeTab === 'IMPACT' ? '3px solid #A6E3A1' : '3px solid transparent',
          }}
        >
          Production Impact
        </button>
      </div>

      {/* Tab Body */}
      <div style={{ flex: 1, overflowY: 'auto', backgroundColor: '#1E1E2E' }}>
        {activeTab === 'VALIDATION' && (
          <ValidationGatePanel
            report={validationReport}
            onSelectEntity={onSelectEntity}
            onLockRevision={onLockRevision}
          />
        )}
        {activeTab === 'PROPOSAL' && (
          <AIProposalView
            activeProposal={activeProposal}
            onRequestProposal={onRequestProposal}
            onApproveProposal={onApproveProposal}
            onRejectProposal={onRejectProposal}
          />
        )}
        {activeTab === 'DIFF' && <ScreenplayDiffView diffResult={diffResult} />}
        {activeTab === 'IMPACT' && <ProductionImpactView impact={impact} />}
      </div>
    </div>
  );
};
