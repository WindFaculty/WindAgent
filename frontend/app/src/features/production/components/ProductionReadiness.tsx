/**
 * P1.7 — Production Readiness panel.
 *
 * Replaces the fake Render / Animate / Generate-Video buttons with the real
 * pre-production gate: a live readiness checklist backed by the P1.6
 * preflight validator, an explicit Finalize action, and the immutable
 * content-addressed package handoff afterwards.
 */
import React, { useState } from 'react';
import {
  useProductionPreflight,
  usePackages,
  useFinalizePackage,
} from '../hooks/useProduction';
import type { PreflightFinding, ProductionTarget } from '@windagent/api-contracts';

interface ProductionReadinessProps {
  episodeId: string;
}

const CHECK_LABELS: { key: string; label: string }[] = [
  { key: 'screenplay_locked', label: 'Screenplay' },
  { key: 'characters_production_ready', label: 'Characters' },
  { key: 'world_canon_present', label: 'World' },
  { key: 'storyboard_synced', label: 'Storyboard' },
  { key: 'shot_plan_pinned', label: 'Shot Plan' },
  { key: 'mandatory_assets_resolved', label: 'Mandatory Assets' },
];

const TARGETS: { value: ProductionTarget; label: string }[] = [
  { value: 'GENERIC_3D', label: 'Generic 3D' },
  { value: 'BLENDER', label: 'Blender' },
  { value: 'UNREAL', label: 'Unreal' },
];

export const ProductionReadiness: React.FC<ProductionReadinessProps> = ({ episodeId }) => {
  // A read-only preflight never mutates; polling keeps the checklist honest.
  const { data: preflight, isLoading, error } = useProductionPreflight(episodeId);
  const { data: packages = [] } = usePackages(episodeId);
  const finalize = useFinalizePackage(episodeId);

  const [target, setTarget] = useState<ProductionTarget>('GENERIC_3D');
  const [showManifestFor, setShowManifestFor] = useState<string | null>(null);
  const [finalizeError, setFinalizeError] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="production-readiness production-readiness--loading">
        <div className="loading-spinner" />
        <p>Đang kiểm tra độ sẵn sàng sản xuất...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="production-readiness production-readiness--error">
        <h3>Không thể tải preflight</h3>
        <p>{(error as Error).message}</p>
      </div>
    );
  }

  if (!preflight) {
    return null;
  }

  const ready = preflight.status === 'READY';
  const latestPackage = packages[0] ?? null;

  const onFinalize = () => {
    setFinalizeError(null);
    finalize.mutate(
      { production_target: target },
      {
        onSuccess: () => setFinalizeError(null),
        onError: (err: any) => {
          // Surface the REAL blockers returned by the API (409 detail).
          const detail = err?.body?.detail ?? err?.detail;
          if (detail?.error_code === 'PREPRODUCTION_NOT_READY') {
            setFinalizeError('Preflight bị chặn — hãy xử lý các mục còn thiếu trước khi đóng gói.');
          } else {
            setFinalizeError(detail?.message ?? String(err));
          }
        },
      }
    );
  };

  return (
    <div className="production-readiness">
      <div className="production-card">
        <h3>{ready ? '✅' : '🚦'} Production Readiness</h3>

        <div className={`production-readiness__status production-readiness__status--${preflight.status.toLowerCase()}`}>
          {ready ? 'READY' : 'BLOCKED'}
        </div>

        <div className="production-stage-checklist">
          {CHECK_LABELS.map(({ key, label }) => {
            const ok = preflight.checks[key] === true;
            return (
              <div key={key} className={`production-stage-item ${ok ? 'done' : ''}`}>
                <span>{label}</span>
                <span aria-label={label}>{ok ? '✅' : '❌'}</span>
              </div>
            );
          })}
        </div>

        {preflight.blocking_findings.length > 0 && (
          <div className="production-readiness__findings">
            <h4>Lý do chặn</h4>
            {preflight.blocking_findings.map((f: PreflightFinding, i: number) => (
              <div key={`${f.code}-${i}`} className="production-readiness__finding">
                <code>{f.code}</code>
                <p>{f.message}</p>
              </div>
            ))}
          </div>
        )}

        {preflight.warnings.length > 0 && (
          <details className="production-readiness__warnings">
            <summary>Cảnh báo ({preflight.warnings.length})</summary>
            {preflight.warnings.map((f: PreflightFinding, i: number) => (
              <div key={`${f.code}-${i}`} className="production-readiness__finding">
                <code>{f.code}</code>
                <p>{f.message}</p>
              </div>
            ))}
          </details>
        )}
      </div>

      {!latestPackage && (
        <div className="production-card">
          <h3>📦 Đóng gói Production Package</h3>
          <p className="empty-hint">
            Package chốt trạng thái pre-production thành bản bàn giao bất biến,
            đánh địa chỉ theo nội dung (package_hash). P1 không chạy engine —
            production_target chỉ là nhãn tiêu thụ ở P2.
          </p>

          <div className="production-readiness__controls">
            <label htmlFor="pkg-target">Production Target:</label>
            <select
              id="pkg-target"
              value={target}
              onChange={(e) => setTarget(e.target.value as ProductionTarget)}
            >
              {TARGETS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>

            <button
              className="btn btn--primary"
              onClick={onFinalize}
              disabled={!ready || finalize.isPending}
              title={ready ? 'Đóng gói và khóa manifest' : 'Preflight chưa READY'}
            >
              {finalize.isPending ? '⏳ Đang đóng gói...' : '[Finalize Production Package]'}
            </button>
          </div>

          {finalizeError && (
            <p className="production-readiness__error">{finalizeError}</p>
          )}
        </div>
      )}

      {packages.map((pkg) => (
        <div key={pkg.package_id} className="delivery-card">
          <h3>📦 PRODUCTION PACKAGE READY</h3>
          <dl className="production-dl">
            <dt>Package</dt>
            <dd><code>{pkg.package_id}</code></dd>
            <dt>Target</dt>
            <dd>{TARGETS.find((t) => t.value === pkg.production_target)?.label ?? pkg.production_target}</dd>
            <dt>Content Hash</dt>
            <dd><code title={pkg.package_hash}>{pkg.package_hash.slice(0, 16)}…</code></dd>
            <dt>Shots</dt>
            <dd>{pkg.shot_plan?.shot_count}</dd>
            <dt>Created</dt>
            <dd>{new Date(pkg.created_at).toLocaleString()}</dd>
          </dl>

          <button
            className="btn btn--secondary btn--sm"
            onClick={() => setShowManifestFor(showManifestFor === pkg.package_id ? null : pkg.package_id)}
          >
            {showManifestFor === pkg.package_id ? '[Ẩn Manifest]' : '[View Manifest]'}
          </button>

          {showManifestFor === pkg.package_id && (
            <pre className="production-readiness__manifest">
              {JSON.stringify(pkg, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
};
