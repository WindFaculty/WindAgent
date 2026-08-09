import React, { useState } from 'react';
import { ScriptRevisionProposalDTO } from '@windagent/production-contracts';

interface AIProposalViewProps {
  activeProposal: ScriptRevisionProposalDTO | null;
  onRequestProposal: (actionType: string, instruction: string) => void;
  onApproveProposal: (proposalId: string) => void;
  onRejectProposal: (proposalId: string) => void;
}

export const AIProposalView: React.FC<AIProposalViewProps> = ({
  activeProposal,
  onRequestProposal,
  onApproveProposal,
  onRejectProposal,
}) => {
  const [actionType, setActionType] = useState<string>('REWRITE');
  const [instruction, setInstruction] = useState<string>('Make action description more vivid');

  return (
    <div style={{ padding: '1rem', fontFamily: 'Inter, system-ui, sans-serif', color: '#CDD6F4' }}>
      {/* Proposal Request Form */}
      <div
        style={{
          display: 'flex',
          gap: '0.75rem',
          alignItems: 'center',
          backgroundColor: '#181825',
          padding: '0.75rem',
          borderRadius: '6px',
          border: '1px solid #313244',
          marginBottom: '1rem',
        }}
      >
        <select
          value={actionType}
          onChange={(e) => setActionType(e.target.value)}
          style={{
            padding: '0.4rem',
            borderRadius: '4px',
            border: '1px solid #45475A',
            backgroundColor: '#1E1E2E',
            color: '#89B4FA',
            fontWeight: 600,
            fontSize: '0.75rem',
          }}
        >
          <option value="REWRITE">Rewrite Tone</option>
          <option value="SHORTEN">Shorten Action</option>
          <option value="EXPAND">Expand Details</option>
          <option value="POLISH_DIALOGUE">Polish Dialogue</option>
        </select>

        <input
          type="text"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Instruction prompt for AI..."
          style={{
            flex: 1,
            padding: '0.4rem 0.6rem',
            borderRadius: '4px',
            border: '1px solid #45475A',
            backgroundColor: '#1E1E2E',
            color: '#F5E0DC',
            fontSize: '0.8rem',
          }}
        />

        <button
          onClick={() => onRequestProposal(actionType, instruction)}
          style={{
            padding: '0.4rem 0.85rem',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: '#CBA6F7',
            color: '#11111B',
            fontWeight: 700,
            fontSize: '0.75rem',
            cursor: 'pointer',
          }}
        >
          ✨ Generate AI Proposal
        </button>
      </div>

      {/* Active Proposal Card */}
      {activeProposal ? (
        <div
          style={{
            backgroundColor: '#181825',
            padding: '1rem',
            borderRadius: '8px',
            border: '1px solid #CBA6F7',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#CBA6F7' }}>
              PROPOSAL {activeProposal.proposal_id} ({activeProposal.action_type})
            </span>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#FAB387' }}>STATUS: {activeProposal.status}</span>
          </div>

          <p style={{ fontSize: '0.8rem', color: '#A6ADC8', margin: '0 0 1rem 0' }}>
            Instruction: "{activeProposal.instruction}"
          </p>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              onClick={() => onApproveProposal(activeProposal.proposal_id)}
              disabled={activeProposal.status !== 'PENDING'}
              style={{
                padding: '0.4rem 1rem',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: activeProposal.status === 'PENDING' ? '#A6E3A1' : '#313244',
                color: activeProposal.status === 'PENDING' ? '#11111B' : '#585B70',
                fontWeight: 700,
                fontSize: '0.75rem',
                cursor: activeProposal.status === 'PENDING' ? 'pointer' : 'default',
              }}
            >
              ✓ Approve & Dispatch Command
            </button>
            <button
              onClick={() => onRejectProposal(activeProposal.proposal_id)}
              disabled={activeProposal.status !== 'PENDING'}
              style={{
                padding: '0.4rem 1rem',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: activeProposal.status === 'PENDING' ? '#F38BA8' : '#313244',
                color: activeProposal.status === 'PENDING' ? '#11111B' : '#585B70',
                fontWeight: 700,
                fontSize: '0.75rem',
                cursor: activeProposal.status === 'PENDING' ? 'pointer' : 'default',
              }}
            >
              ✕ Reject Proposal
            </button>
          </div>
        </div>
      ) : (
        <div style={{ color: '#6C7086', fontSize: '0.8rem' }}>No AI proposal active. Click Generate to request a candidate proposal.</div>
      )}
    </div>
  );
};
