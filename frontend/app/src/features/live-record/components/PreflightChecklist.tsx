/**
 * PreflightChecklist — Phase E cutover (ban_ke_hoach_v1.md Section 23).
 *
 * The 13 frozen preflight guards rendered as a READY/BLOCKED checklist.
 * Inputs are the raw guard booleans; classification stays in
 * `domain/stateMachine.evaluatePreflight` — this component never re-implements it.
 */

import React from 'react';
import { CheckCircle2, ShieldAlert, ClipboardCheck } from 'lucide-react';
import { evaluatePreflight } from '../domain/stateMachine';

export type PreflightChecks = Parameters<typeof evaluatePreflight>[0];

export interface PreflightChecklistProps {
  readonly checks: PreflightChecks;
}

const GUARD_LABELS: ReadonlyArray<{ key: keyof PreflightChecks; label: string }> = [
  { key: 'episodeRevisionOk', label: 'Episode revision khớp plan' },
  { key: 'planFrozen', label: 'Plan đã FROZEN' },
  { key: 'planStale', label: 'Plan không stale' },
  { key: 'workspaceHashOk', label: 'Workspace hash khớp' },
  { key: 'artifactsPresent', label: 'Artifact đầy đủ' },
  { key: 'actionsUntampered', label: 'Action không bị can thiệp' },
  { key: 'privacyScanPassed', label: 'Privacy scan đạt (không secret trong vùng quay)' },
  { key: 'providerResolved', label: 'Provider LIVE_DIRECTOR resolved' },
  { key: 'credentialValid', label: 'Credential hợp lệ' },
  { key: 'liveConnectivityOk', label: 'Gemini Live kết nối được' },
  { key: 'recorderHealthy', label: 'Recorder sidecar healthy' },
  { key: 'wgcAvailable', label: 'Capture (ddagrab/WGC) sẵn sàng' },
  { key: 'nvencAvailable', label: 'NVENC sẵn sàng' },
  { key: 'diskSufficient', label: 'Dung lượng đĩa đủ' },
  { key: 'outputWritable', label: 'Thư mục output ghi được' },
];

export const PreflightChecklist: React.FC<PreflightChecklistProps> = ({ checks }) => {
  // `planStale` is an inverted guard (true = blocker) — flip for display.
  const result = evaluatePreflight(checks);

  return (
    <div
      style={{
        backgroundColor: 'rgba(15, 23, 42, 0.8)',
        border: `1px solid ${result.ok ? 'rgba(34, 197, 94, 0.35)' : 'rgba(239, 68, 68, 0.4)'}`,
        borderRadius: '14px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
      data-testid="preflight-checklist"
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#93c5fd', fontWeight: 700, fontSize: '13px' }}>
          <ClipboardCheck size={15} /> Preflight ghi hình
        </div>
        <span
          style={{
            padding: '3px 12px',
            borderRadius: '9999px',
            fontSize: '11px',
            fontWeight: 800,
            letterSpacing: '0.6px',
            color: result.ok ? '#4ade80' : '#fca5a5',
            border: `1px solid ${result.ok ? 'rgba(34, 197, 94, 0.5)' : 'rgba(239, 68, 68, 0.5)'}`,
          }}
        >
          {result.ok ? 'READY' : `BLOCKED · ${result.blockers.length}`}
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {GUARD_LABELS.map(({ key, label }) => {
          const inverted = key === 'planStale';
          const pass = inverted ? !checks[key] : checks[key];
          return (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
              {pass ? (
                <CheckCircle2 size={13} color="#22c55e" />
              ) : (
                <ShieldAlert size={13} color="#ef4444" />
              )}
              <span style={{ color: pass ? '#cbd5e1' : '#fca5a5' }}>{label}</span>
            </div>
          );
        })}
      </div>

      {!result.ok && (
        <div style={{ borderTop: '1px solid rgba(148, 163, 184, 0.15)', paddingTop: '8px' }}>
          {result.blockers.map((b) => (
            <div key={b.code} style={{ fontSize: '11px', color: '#fca5a5', lineHeight: 1.6 }}>
              [{b.code}] {b.message}
              {b.recoverable ? '' : ' — FATAL'}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default PreflightChecklist;
