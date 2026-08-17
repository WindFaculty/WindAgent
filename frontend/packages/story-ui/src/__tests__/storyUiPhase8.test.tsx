import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';
import { ReviewReportView, RevisionProposalView, ApprovalBar, LockReceiptView, LockPackageView } from '../index';

const SAMPLE_REVIEW: StudioArtifactEnvelope = {
  artifact_id: 'art_rev_1',
  artifact_type: 'ReviewReport',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'review123hash',
  revision_id: 'rev_fixture',
  created_at: '2026-08-01T00:00:00Z',
  content: {
    verdict: 'REVISION_REQUIRED',
    quality_summary: 'Kịch bản tốt nhưng cần chỉnh nhịp điệu ở cảnh 2.',
    review_iteration: 1,
    maximum_iterations: 3,
    dimensions: [
      { dimension: 'Plot', score: 0.95, blocking: false },
      { dimension: 'Pacing', score: 0.65, blocking: true, note: 'Nhịp điệu quá chậm' },
    ],
    findings: [
      {
        code: 'FIND_01',
        dimension: 'Pacing',
        severity: 'BLOCKING',
        location: 'Scene 2',
        evidence: 'Đoạn hội thoại kéo dài 40 giây không có chuyển biến.',
        remediation: 'Cắt bớt 2 câu thoại thừa.',
      },
      {
        code: 'FIND_02',
        dimension: 'Dialogue',
        severity: 'MAJOR',
        location: 'Scene 1',
        evidence: 'Lời thoại chưa tự nhiên.',
        remediation: 'Thay thế bằng câu từ gần gũi.',
      },
    ],
  },
};

const SAMPLE_REVISION_PROPOSAL: StudioArtifactEnvelope = {
  artifact_id: 'art_prop_1',
  artifact_type: 'RevisionProposal',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'prop123hash',
  revision_id: 'rev_2',
  created_at: '2026-08-01T00:00:00Z',
  content: {
    proposal_id: 'prop_1',
    draft_id: 'draft_1',
    revision_reason: 'Cắt bớt thoại thừa theo yêu cầu review.',
    accepted_finding_codes: ['FIND_01', 'FIND_02'],
    iteration_number: 2,
    maximum_iterations: 3,
  },
};

const SAMPLE_LOCK_RECEIPT: StudioArtifactEnvelope = {
  artifact_id: 'art_receipt_1',
  artifact_type: 'LockedScreenplayReceipt',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'receipt123hash',
  revision_id: 'rev_fixture',
  created_at: '2026-08-01T00:00:00Z',
  content: {
    receipt_id: 'rec_1001',
    draft_id: 'draft_2',
    state: 'READY_FOR_PRODUCTION',
    issued_at: '2026-08-13T10:00:00Z',
    policy_id: 'policy_strict_v1',
    approval_mode: 'MANUAL',
  },
};

const SAMPLE_LOCK_PACKAGE: StudioArtifactEnvelope = {
  artifact_id: 'art_pkg_1',
  artifact_type: 'LockedScreenplayPackage',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'pkg123hash',
  revision_id: 'rev_fixture',
  created_at: '2026-08-01T00:00:00Z',
  content: {
    package_id: 'pkg_5001',
    assembled_at: '2026-08-13T10:05:00Z',
    manifest: [
      { artifact_type: 'ScreenplayDraft', artifact_id: 'art_sp_2', content_hash: 'sphash9999', revision_id: 'rev_2' },
      { artifact_type: 'StoryBible', artifact_id: 'art_sb_1', content_hash: 'sbhash8888', revision_id: 'rev_1' },
    ],
  },
};

describe('Phase UI8 — Review, Revision, Approval & Lock UX', () => {
  afterEach(cleanup);

  it('renders ReviewReportView with dimensions grid and categorized findings', () => {
    render(<ReviewReportView artifact={SAMPLE_REVIEW} />);

    expect(screen.getByText('Review Report')).toBeInTheDocument();
    expect(screen.getByText('REVISION_REQUIRED')).toBeInTheDocument();
    expect(screen.getByText('Iteration 1/3')).toBeInTheDocument();

    // Dimensions
    expect(screen.getByText('Plot')).toBeInTheDocument();
    expect(screen.getByText('0.95')).toBeInTheDocument();
    expect(screen.getAllByText('Pacing').length).toBeGreaterThan(0);
    expect(screen.getByText('0.65')).toBeInTheDocument();

    // Findings
    expect(screen.getByText(/BLOCKING FINDINGS/)).toBeInTheDocument();
    expect(screen.getByText('FIND_01')).toBeInTheDocument();
    expect(screen.getByText(/Đoạn hội thoại kéo dài 40 giây/)).toBeInTheDocument();
    expect(screen.getByText(/MAJOR FINDINGS/)).toBeInTheDocument();
    expect(screen.getByText('FIND_02')).toBeInTheDocument();
  });

  it('renders RevisionProposalView with version badge and addressed findings', () => {
    render(<RevisionProposalView artifact={SAMPLE_REVISION_PROPOSAL} />);

    expect(screen.getByText('Revision rev_2')).toBeInTheDocument();
    expect(screen.getByText(/Cắt bớt thoại thừa/)).toBeInTheDocument();
    expect(screen.getByText('✓ FIND_01')).toBeInTheDocument();
    expect(screen.getByText('✓ FIND_02')).toBeInTheDocument();
  });

  it('renders ApprovalBar and triggers submit callbacks', () => {
    const handleSubmit = vi.fn();
    render(
      <ApprovalBar
        checkpoint="SCREENPLAY_REVIEW"
        artifactTitle="Kịch Bản Tập 1"
        revisionId="rev_2"
        revisionHash="sp123hash999"
        expectedVersion={3}
        onSubmit={handleSubmit}
      />
    );

    expect(screen.getByText(/Approval/i)).toBeInTheDocument();
    expect(screen.getByText('SCREENPLAY_REVIEW')).toBeInTheDocument();

    const approveBtn = screen.getByRole('button', { name: 'Approve SCREENPLAY_REVIEW' });
    fireEvent.click(approveBtn);
    expect(handleSubmit).toHaveBeenCalledWith('APPROVED', '');
  });

  it('renders LockReceiptView and LockPackageView with handoff lineage', () => {
    render(
      <div>
        <LockReceiptView artifact={SAMPLE_LOCK_RECEIPT} />
        <LockPackageView artifact={SAMPLE_LOCK_PACKAGE} />
      </div>
    );

    expect(screen.getByText('✓ Locked for Production')).toBeInTheDocument();
    expect(screen.getByText('READY_FOR_PRODUCTION')).toBeInTheDocument();
    expect(screen.getByText('rec_1001')).toBeInTheDocument();
    expect(screen.getByText('Locked package — lineage & checksums')).toBeInTheDocument();
    expect(screen.getByText(/pkg_5001/)).toBeInTheDocument();
    expect(screen.getByText('art_sp_2')).toBeInTheDocument();
  });
});
