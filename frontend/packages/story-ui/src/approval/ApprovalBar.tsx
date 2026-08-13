import { useState } from 'react';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';

const MUTED = { color: '#94a3b8' } as const;

function Badge({ children, color = '#334155', textColor = '#e2e8f0' }: { children: React.ReactNode; color?: string; textColor?: string }) {
  return (
    <span style={{ background: color, color: textColor, fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 12, display: 'inline-block' }}>
      {children}
    </span>
  );
}

function ArtifactHeader({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const hash = artifact.content_hash ?? '';
  return (
    <div style={{ fontSize: 12, marginBottom: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
      <Badge color="#0284c7">{artifact.artifact_type}</Badge>
      <span style={MUTED}>
        · rev {artifact.revision_id ?? '—'} · hash {hash.slice(0, 12)}…
        {artifact.status ? ` · ${artifact.status}` : ''}
      </span>
    </div>
  );
}

export type ApprovalDecision = 'APPROVED' | 'REJECTED' | 'REQUEST_REVISION';

export interface ApprovalBarProps {
  checkpoint: string;
  artifactTitle: string | null;
  revisionId: string | null;
  revisionHash: string | null;
  expectedVersion: number;
  disabled?: boolean;
  onSubmit: (decision: ApprovalDecision, reason: string) => void;
}

export function ApprovalBar({
  checkpoint,
  artifactTitle,
  revisionId,
  revisionHash,
  expectedVersion,
  disabled,
  onSubmit,
}: ApprovalBarProps) {
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
      style={{
        border: '1px solid #fbbf24',
        borderRadius: 8,
        padding: 14,
        margin: '8px 0',
        background: 'rgba(251, 191, 36, 0.05)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Badge color="#78350f" textColor="#fbbf24">Approval required</Badge>
          <span style={{ fontWeight: 700, fontSize: 15, color: '#e2e8f0' }}>{checkpoint}</span>
          {artifactTitle && <span style={{ color: '#cbd5e1', fontSize: 13 }}>{artifactTitle}</span>}
        </div>
        {revisionHash && <span style={{ color: '#94a3b8', fontSize: 12 }}>hash {revisionHash.slice(0, 12)}…</span>}
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
        <button
          onClick={() => submit('APPROVED')}
          disabled={disabled || busy !== null}
          aria-label={`Approve ${checkpoint}`}
          style={{
            padding: '6px 16px',
            borderRadius: 6,
            border: 'none',
            background: disabled ? '#334155' : '#166534',
            color: disabled ? '#94a3b8' : '#ffffff',
            fontWeight: 600,
            cursor: disabled ? 'not-allowed' : 'pointer',
          }}
        >
          Approve
        </button>

        <button
          onClick={() => submit('REQUEST_REVISION')}
          disabled={disabled || busy !== null}
          aria-label={`Request revision at ${checkpoint}`}
          style={{
            padding: '6px 16px',
            borderRadius: 6,
            border: 'none',
            background: disabled ? '#334155' : '#854d0e',
            color: disabled ? '#94a3b8' : '#ffffff',
            fontWeight: 600,
            cursor: disabled ? 'not-allowed' : 'pointer',
          }}
        >
          Request revision
        </button>

        <button
          onClick={() => submit('REJECTED')}
          disabled={disabled || busy !== null}
          aria-label={`Reject ${checkpoint}`}
          style={{
            padding: '6px 16px',
            borderRadius: 6,
            border: 'none',
            background: disabled ? '#334155' : '#991b1b',
            color: disabled ? '#94a3b8' : '#ffffff',
            fontWeight: 600,
            cursor: disabled ? 'not-allowed' : 'pointer',
          }}
        >
          Reject
        </button>
      </div>

      <textarea
        aria-label="Approval reason"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Reason / Feedback notes (optional for Approve, recommended for Revision/Reject)..."
        rows={2}
        style={{
          width: '100%',
          marginTop: 10,
          boxSizing: 'border-box',
          resize: 'vertical',
          background: '#0f172a',
          border: '1px solid #334155',
          borderRadius: 6,
          padding: 8,
          color: '#e2e8f0',
          fontSize: 13,
        }}
      />

      {revisionId && (
        <div style={{ color: '#94a3b8', fontSize: 12, marginTop: 6 }}>
          revision {revisionId} · version {expectedVersion}
        </div>
      )}
    </section>
  );
}

export interface LockReceiptContent {
  receipt_id?: string;
  draft_id?: string;
  state?: string;
  issued_at?: string;
  policy_id?: string;
  approval_mode?: string;
}

export function LockReceiptView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = (artifact.content as LockReceiptContent) ?? {};
  return (
    <div style={{ border: '1px solid #166534', borderRadius: 8, padding: 14, background: 'rgba(22, 101, 52, 0.08)' }}>
      <ArtifactHeader artifact={artifact} />
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        <Badge color="#14532d" textColor="#4ade80">✓ Locked for Production</Badge>
        <span style={{ color: '#4ade80', fontWeight: 700, fontSize: 16 }}>{c.state ?? 'READY_FOR_PRODUCTION'}</span>
      </div>
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 16px', margin: 0, fontSize: 13 }}>
        <dt style={{ color: '#94a3b8' }}>Receipt ID</dt><dd style={{ margin: 0, fontWeight: 600, color: '#e2e8f0' }}>{c.receipt_id}</dd>
        <dt style={{ color: '#94a3b8' }}>Draft ID</dt><dd style={{ margin: 0, color: '#cbd5e1' }}>{c.draft_id}</dd>
        {c.issued_at && <><dt style={{ color: '#94a3b8' }}>Issued At</dt><dd style={{ margin: 0, color: '#cbd5e1' }}>{c.issued_at}</dd></>}
        {c.policy_id && <><dt style={{ color: '#94a3b8' }}>Policy ID</dt><dd style={{ margin: 0, color: '#cbd5e1' }}>{c.policy_id}</dd></>}
        {c.approval_mode && <><dt style={{ color: '#94a3b8' }}>Approval Mode</dt><dd style={{ margin: 0, color: '#cbd5e1' }}>{c.approval_mode}</dd></>}
      </dl>
    </div>
  );
}

export interface LockPackageContent {
  package_id?: string;
  receipt_id?: string;
  assembled_at?: string;
  manifest?: Array<{ artifact_type?: string; artifact_id?: string; content_hash?: string; revision_id?: string | null }>;
}

export function LockPackageView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = (artifact.content as LockPackageContent) ?? {};
  const manifest = c.manifest ?? [];
  return (
    <div style={{ border: '1px solid #0284c7', borderRadius: 8, padding: 14, background: 'rgba(2, 132, 199, 0.05)' }}>
      <ArtifactHeader artifact={artifact} />
      <div style={{ fontWeight: 700, fontSize: 16, color: '#e2e8f0', marginBottom: 4 }}>
        Locked package — lineage &amp; checksums
      </div>
      {c.package_id && <div style={{ ...MUTED, fontSize: 12, marginBottom: 8 }}>package {c.package_id}{c.assembled_at ? ` · assembled ${c.assembled_at}` : ''}</div>}
      
      <div style={{ background: '#0f172a', borderRadius: 6, padding: 10, border: '1px solid #334155' }}>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 12 }}>
          {manifest.map((m) => (
            <li key={m.artifact_id ?? m.artifact_type} style={{ padding: '4px 0', borderBottom: '1px solid #1e293b', display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <span style={{ fontWeight: 600, color: '#7dd3fc' }}>{m.artifact_type}</span>
              <span style={{ color: '#cbd5e1' }}>{m.artifact_id}</span>
              <span style={MUTED}>hash {m.content_hash?.slice(0, 12)}…</span>
              {m.revision_id ? <span style={MUTED}>rev {m.revision_id}</span> : null}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
