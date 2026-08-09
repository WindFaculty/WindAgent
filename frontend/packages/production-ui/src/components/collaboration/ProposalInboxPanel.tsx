import React, { useState } from 'react';
import { ProductionChangeProposal, ProposalStatus } from '@windagent/production-contracts';

export interface ProposalInboxPanelProps {
  proposals: ProductionChangeProposal[];
  onApprove: (proposalId: string, reason: string) => Promise<void>;
  onReject: (proposalId: string, reason: string) => Promise<void>;
  onSelectProposal?: (proposal: ProductionChangeProposal) => void;
  isLoading?: boolean;
}

export const ProposalInboxPanel: React.FC<ProposalInboxPanelProps> = ({
  proposals,
  onApprove,
  onReject,
  onSelectProposal,
  isLoading = false,
}) => {
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(
    proposals.length > 0 ? proposals[0].proposal_id : null
  );
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [rejectReason, setRejectReason] = useState<string>('');
  const [showRejectModal, setShowRejectModal] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const filteredProposals = proposals.filter((p) => {
    if (filterStatus === 'ALL') return true;
    return p.status === filterStatus;
  });

  const activeProposal = proposals.find((p) => p.proposal_id === selectedProposalId) || filteredProposals[0];

  const handleApprove = async () => {
    if (!activeProposal) return;
    setIsSubmitting(true);
    try {
      await onApprove(activeProposal.proposal_id, 'Approved via Human Control UI');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRejectConfirm = async () => {
    if (!activeProposal || !rejectReason.trim()) return;
    setIsSubmitting(true);
    try {
      await onReject(activeProposal.proposal_id, rejectReason.trim());
      setShowRejectModal(false);
      setRejectReason('');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getStatusBadgeStyle = (status: ProposalStatus) => {
    switch (status) {
      case 'PENDING':
        return { background: '#f59e0b22', color: '#f59e0b', border: '1px solid #f59e0b44' };
      case 'REQUIRES_REVIEW':
        return { background: '#ef444422', color: '#ef4444', border: '1px solid #ef444444' };
      case 'APPROVED':
        return { background: '#10b98122', color: '#10b981', border: '1px solid #10b98144' };
      case 'REJECTED':
        return { background: '#6b728022', color: '#9ca3af', border: '1px solid #6b728044' };
      default:
        return { background: '#37415122', color: '#9ca3af', border: '1px solid #37415144' };
    }
  };

  return (
    <div style={{ display: 'flex', height: '100%', background: '#0f172a', color: '#f8fafc', borderRadius: 8, overflow: 'hidden', border: '1px solid #1e293b' }}>
      {/* Sidebar / List */}
      <div style={{ width: 340, borderRight: '1px solid #1e293b', display: 'flex', flexDirection: 'column', background: '#090d16' }}>
        <div style={{ padding: '16px', borderBottom: '1px solid #1e293b' }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#f8fafc' }}>
            Change Proposals Inbox
          </h3>
          <p style={{ margin: '4px 0 12px 0', fontSize: 12, color: '#94a3b8' }}>
            Human Production Control Layer (UI37)
          </p>
          {/* Filters */}
          <div style={{ display: 'flex', gap: 6 }}>
            {['ALL', 'PENDING', 'REQUIRES_REVIEW', 'APPROVED', 'REJECTED'].map((st) => (
              <button
                key={st}
                onClick={() => setFilterStatus(st)}
                style={{
                  padding: '4px 8px',
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 500,
                  cursor: 'pointer',
                  border: 'none',
                  background: filterStatus === st ? '#3b82f6' : '#1e293b',
                  color: filterStatus === st ? '#ffffff' : '#94a3b8',
                }}
              >
                {st}
              </button>
            ))}
          </div>
        </div>

        {/* Proposals List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
          {isLoading ? (
            <div style={{ padding: 16, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Loading proposals...</div>
          ) : filteredProposals.length === 0 ? (
            <div style={{ padding: 16, textAlign: 'center', color: '#64748b', fontSize: 13 }}>No proposals found.</div>
          ) : (
            filteredProposals.map((p) => {
              const isSelected = activeProposal?.proposal_id === p.proposal_id;
              const badgeStyle = getStatusBadgeStyle(p.status);
              return (
                <div
                  key={p.proposal_id}
                  onClick={() => {
                    setSelectedProposalId(p.proposal_id);
                    if (onSelectProposal) onSelectProposal(p);
                  }}
                  style={{
                    padding: 12,
                    borderRadius: 6,
                    marginBottom: 6,
                    cursor: 'pointer',
                    background: isSelected ? '#1e293b' : 'transparent',
                    border: isSelected ? '1px solid #3b82f6' : '1px solid transparent',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: '#38bdf8' }}>
                      {p.proposal_type}
                    </span>
                    <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, ...badgeStyle }}>
                      {p.status}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: '#e2e8f0', marginBottom: 4 }}>
                    Proposal ID: <code style={{ color: '#a5f3fc' }}>{p.proposal_id}</code>
                  </div>
                  <div style={{ fontSize: 11, color: '#94a3b8', display: 'flex', justifyContent: 'space-between' }}>
                    <span>Actor: {p.created_by_agent}</span>
                    <span>Rev: {p.target_revision_id}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Main Detail View */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {activeProposal ? (
          <>
            {/* Header */}
            <div style={{ padding: 16, borderBottom: '1px solid #1e293b', background: '#0f172a', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <h4 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Proposal {activeProposal.proposal_id}</h4>
                  <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, ...getStatusBadgeStyle(activeProposal.status) }}>
                    {activeProposal.status}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: '#94a3b8' }}>
                  Project: {activeProposal.project_id} | Target Rev: {activeProposal.target_revision_id} (Seq: {activeProposal.base_sequence}) | Creator: {activeProposal.created_by_agent}
                </div>
              </div>

              {/* Action buttons */}
              {activeProposal.status === 'PENDING' && (
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    disabled={isSubmitting}
                    onClick={() => setShowRejectModal(true)}
                    style={{
                      padding: '8px 16px',
                      borderRadius: 6,
                      background: '#dc2626',
                      color: '#fff',
                      border: 'none',
                      fontSize: 13,
                      fontWeight: 500,
                      cursor: 'pointer',
                      opacity: isSubmitting ? 0.6 : 1,
                    }}
                  >
                    Reject
                  </button>
                  <button
                    disabled={isSubmitting}
                    onClick={handleApprove}
                    style={{
                      padding: '8px 16px',
                      borderRadius: 6,
                      background: '#16a34a',
                      color: '#fff',
                      border: 'none',
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: 'pointer',
                      opacity: isSubmitting ? 0.6 : 1,
                    }}
                  >
                    Approve & Execute
                  </button>
                </div>
              )}
            </div>

            {/* Warning Banner if Stale */}
            {activeProposal.status === 'REQUIRES_REVIEW' && (
              <div style={{ padding: 12, background: '#ef444415', borderBottom: '1px solid #ef444444', color: '#fca5a5', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
                <strong>⚠️ Stale Proposal Notice:</strong> Target sequence has advanced. Human review or re-computation is required before approval.
              </div>
            )}

            {/* Proposal Content Body */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
              {/* Content Hash & Integrity */}
              <div style={{ marginBottom: 16, padding: 12, borderRadius: 6, background: '#1e293b', border: '1px solid #334155' }}>
                <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 4 }}>Content SHA-256 Integrity Hash</div>
                <code style={{ fontSize: 11, color: '#a5f3fc', wordBreak: 'break-all' }}>{activeProposal.hash}</code>
              </div>

              {/* Semantic Diff */}
              <div style={{ marginBottom: 16 }}>
                <h5 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#cbd5e1' }}>Semantic Diff Summary</h5>
                <pre style={{ margin: 0, padding: 12, borderRadius: 6, background: '#020617', border: '1px solid #1e293b', fontSize: 12, color: '#e2e8f0', overflowX: 'auto' }}>
                  {JSON.stringify(activeProposal.diff || {}, null, 2)}
                </pre>
              </div>

              {/* Downstream Impact */}
              <div style={{ marginBottom: 16 }}>
                <h5 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#cbd5e1' }}>Downstream Production Impact</h5>
                <pre style={{ margin: 0, padding: 12, borderRadius: 6, background: '#020617', border: '1px solid #1e293b', fontSize: 12, color: '#e2e8f0', overflowX: 'auto' }}>
                  {JSON.stringify(activeProposal.impact || {}, null, 2)}
                </pre>
              </div>

              {/* Proposed Candidate Payload */}
              <div>
                <h5 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#cbd5e1' }}>Candidate Payload</h5>
                <pre style={{ margin: 0, padding: 12, borderRadius: 6, background: '#020617', border: '1px solid #1e293b', fontSize: 12, color: '#38bdf8', overflowX: 'auto' }}>
                  {JSON.stringify(activeProposal.candidate || {}, null, 2)}
                </pre>
              </div>
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
            Select a proposal to inspect details.
          </div>
        )}
      </div>

      {/* Reject Reason Modal */}
      {showRejectModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ width: 440, background: '#0f172a', borderRadius: 8, padding: 20, border: '1px solid #334155' }}>
            <h4 style={{ margin: '0 0 12px 0', fontSize: 16, color: '#f8fafc' }}>Reject Proposal Reason</h4>
            <p style={{ fontSize: 13, color: '#94a3b8', margin: '0 0 12px 0' }}>
              Please provide a clear explanation for rejecting proposal <code style={{ color: '#38bdf8' }}>{activeProposal?.proposal_id}</code>.
            </p>
            <textarea
              rows={4}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason for rejection..."
              style={{
                width: '100%',
                padding: 10,
                borderRadius: 6,
                background: '#020617',
                border: '1px solid #334155',
                color: '#f8fafc',
                fontSize: 13,
                resize: 'none',
                marginBottom: 16,
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                onClick={() => setShowRejectModal(false)}
                style={{ padding: '6px 12px', borderRadius: 4, background: '#334155', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 13 }}
              >
                Cancel
              </button>
              <button
                disabled={!rejectReason.trim() || isSubmitting}
                onClick={handleRejectConfirm}
                style={{ padding: '6px 12px', borderRadius: 4, background: '#dc2626', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 13, opacity: !rejectReason.trim() ? 0.5 : 1 }}
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
