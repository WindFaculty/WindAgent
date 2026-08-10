/**
 * Approval checkpoint controls (Plan C4) — approve / request-revision /
 * reject at IDEA, STORY_BIBLE, and OUTLINE checkpoints.
 *
 * Rendered only when the episode server state permits (awaiting_checkpoint
 * set); the decision and exact revision/hash are submitted to the server —
 * this view never advances state locally.
 */

import { useState } from 'react';

export type ApprovalDecision = 'APPROVED' | 'REJECTED' | 'REQUEST_REVISION';

export function ApprovalBar({
  checkpoint,
  artifactTitle,
  revisionId,
  revisionHash,
  expectedVersion,
  disabled,
  onSubmit,
}: {
  checkpoint: string;
  artifactTitle: string | null;
  revisionId: string | null;
  revisionHash: string | null;
  expectedVersion: number;
  disabled?: boolean;
  onSubmit: (decision: ApprovalDecision, reason: string) => void;
}) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState<ApprovalDecision | null>(null);

  const submit = (decision: ApprovalDecision) => {
    setBusy(decision);
    onSubmit(decision, reason.trim());
    setBusy(null);
  };

  return (
    <section
      aria-label={`Approval checkpoint ${checkpoint}`}
      style={{ border: '1px solid #fbbf24', borderRadius: 8, padding: 10, margin: '8px 0' }}
    >
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <b>Approval required</b>
        <span>{checkpoint}</span>
        {artifactTitle && <span style={{ color: '#94a3b8' }}>{artifactTitle}</span>}
        {revisionHash && <span style={{ color: '#94a3b8', fontSize: 12 }}>hash {revisionHash.slice(0, 12)}…</span>}
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        <button
          onClick={() => submit('APPROVED')}
          disabled={disabled || busy !== null}
          aria-label={`Approve ${checkpoint}`}
        >
          Approve
        </button>
        <button
          onClick={() => submit('REQUEST_REVISION')}
          disabled={disabled || busy !== null}
          aria-label={`Request revision at ${checkpoint}`}
        >
          Request revision
        </button>
        <button
          onClick={() => submit('REJECTED')}
          disabled={disabled || busy !== null}
          aria-label={`Reject ${checkpoint}`}
        >
          Reject
        </button>
      </div>
      <textarea
        aria-label="Approval reason"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Reason (optional for approve, recommended for revision/reject)"
        rows={2}
        style={{ width: '100%', marginTop: 8, boxSizing: 'border-box', resize: 'vertical' }}
      />
      {revisionId && (
        <div style={{ color: '#94a3b8', fontSize: 12, marginTop: 4 }}>
          revision {revisionId} · version {expectedVersion}
        </div>
      )}
    </section>
  );
}
