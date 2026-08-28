/**
 * DeviceSettingsPanel — Phase 13 cutover (ban_ke_hoach_v1.md §17).
 *
 * Every control edits the REAL `RecordingEngineProfile` that reaches the
 * native engine's fail-closed validator — no camera/webcam entries, no fixed
 * bitrate (quality is NVENC CQP), no MP4/ProRes container options (MKV is
 * the master; export formats belong to post-production).
 */

import React from 'react';
import { ChevronDown, Folder, CheckCircle, ShieldAlert } from 'lucide-react';
import type { RecordingEngineProfile } from '../contracts/recordingEngine';
import type { CaptureSources } from '../contracts/ipc';

export interface DeviceSettingsPanelProps {
  /** The live engine profile — single source of truth for this panel. */
  readonly profile: RecordingEngineProfile;
  readonly onProfileChange: (next: RecordingEngineProfile) => void;
  /** Real monitor/window enumeration from the engine (§17); null = not probed yet. */
  readonly sources: CaptureSources | null;
  /** From the capability probe — honest encoder availability, never assumed. */
  readonly nvencReady: boolean;
  readonly savePath: string;
  readonly onOpenSettings: () => void;
}

const RESOLUTION_OPTIONS: ReadonlyArray<{ label: string; width: number; height: number }> = [
  { label: '1920 x 1080 (Full HD)', width: 1920, height: 1080 },
  { label: '3840 x 2160 (4K UHD)', width: 3840, height: 2160 },
  { label: '1280 x 720 (HD)', width: 1280, height: 720 },
];

const CQ_OPTIONS: ReadonlyArray<{ label: string; cq: number }> = [
  { label: '14 · Cực cao', cq: 14 },
  { label: '16 · Cao (mặc định)', cq: 16 },
  { label: '18 · Cân bằng', cq: 18 },
  { label: '20 · Nhẹ', cq: 20 },
];

/** Stable select key for a capture source across DISPLAY/WINDOW kinds. */
function sourceKey(kind: string, id: string): string {
  return `${kind}:${id}`;
}

export const DeviceSettingsPanel: React.FC<DeviceSettingsPanelProps> = ({
  profile,
  onProfileChange,
  sources,
  nvencReady,
  savePath,
  onOpenSettings,
}) => {
  const patchVideo = (partial: Partial<RecordingEngineProfile['video']>): void =>
    onProfileChange({ ...profile, video: { ...profile.video, ...partial } });
  const patchAudio = (partial: Partial<RecordingEngineProfile['audio']>): void =>
    onProfileChange({ ...profile, audio: { ...profile.audio, ...partial } });
  const patchContainer = (partial: Partial<RecordingEngineProfile['container']>): void =>
    onProfileChange({ ...profile, container: { ...profile.container, ...partial } });

  const activeSourceKey = sourceKey(profile.capture_source.kind, profile.capture_source.id);

  const changeCaptureSource = (key: string): void => {
    const idx = key.indexOf(':');
    const kind = key.slice(0, idx);
    const id = key.slice(idx + 1);
    if ((kind === 'DISPLAY' || kind === 'WINDOW') && sources !== null) {
      onProfileChange({ ...profile, capture_source: { kind, id } });
    }
  };

  return (
    <div
      style={{
        backgroundColor: '#0c1322',
        border: '1px solid rgba(59, 130, 246, 0.2)',
        borderRadius: '16px',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        boxShadow: '0 8px 24px -6px rgba(0, 0, 0, 0.5)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingBottom: '10px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>
            Cài Đặt Thiết Bị &amp; Ghi Hình
          </h3>
          <span style={{ fontSize: '11px', color: '#94a3b8' }}>
            NVENC direct · MKV segmented · WGC capture
          </span>
        </div>
        <button
          onClick={onOpenSettings}
          style={{
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: 'rgba(59, 130, 246, 0.15)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            color: '#60a5fa',
            fontSize: '12px',
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
        >
          Sửa
        </button>
      </div>

      {/* Settings rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
        {/* ── Nguồn ghi (§17: monitors + application windows ONLY) ── */}
        <Row label="Nguồn ghi hình">
          <Select
            value={activeSourceKey}
            onChange={changeCaptureSource}
            disabled={sources === null}
          >
            {sources === null && (
              <option value="DISPLAY:">Màn hình chính</option>
            )}
            {sources !== null && (
              <>
                <optgroup label="Màn hình">
                  {sources.monitors.map((m) => (
                    <option key={`m-${m.id}`} value={sourceKey('DISPLAY', m.id)}>
                      {m.label}
                      {m.is_primary ? ' (chính)' : ''}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Cửa sổ ứng dụng">
                  {sources.windows.map((w) => (
                    <option key={`w-${w.id}`} value={sourceKey('WINDOW', w.id)}>
                      {w.label}
                    </option>
                  ))}
                </optgroup>
              </>
            )}
          </Select>
        </Row>

        {/* Độ phân giải */}
        <Row label="Độ phân giải">
          <Select
            value={`${profile.video.width}x${profile.video.height}`}
            onChange={(v) => {
              const found = RESOLUTION_OPTIONS.find((r) => `${r.width}x${r.height}` === v);
              if (found) patchVideo({ width: found.width, height: found.height });
            }}
          >
            {RESOLUTION_OPTIONS.map((r) => (
              <option key={r.label} value={`${r.width}x${r.height}`}>
                {r.label}
              </option>
            ))}
          </Select>
        </Row>

        {/* FPS */}
        <Row label="FPS">
          <Select
            value={String(profile.video.fps)}
            onChange={(v) => patchVideo({ fps: Number(v) === 30 ? 30 : 60 })}
          >
            <option value="60">60</option>
            <option value="30">30</option>
          </Select>
        </Row>

        {/* Codec */}
        <Row label="Codec">
          <Select
            value={profile.video.codec}
            onChange={(v) => patchVideo({ codec: v === 'HEVC' ? 'HEVC' : 'H264' })}
          >
            <option value="H264">H.264 (NVENC)</option>
            <option value="HEVC">HEVC (NVENC)</option>
          </Select>
        </Row>

        {/* Chất lượng — NVENC CQP constant-quality, không bitrate cố định */}
        <Row label="Chất lượng (CQP)">
          <Select
            value={String(profile.video.cq)}
            onChange={(v) => patchVideo({ cq: Number(v) })}
          >
            {CQ_OPTIONS.map((q) => (
              <option key={q.cq} value={String(q.cq)}>
                {q.label}
              </option>
            ))}
          </Select>
        </Row>

        {/* Tự động chia file — MKV segment duration */}
        <Row label="Tự động chia file">
          <Select
            value={String(profile.container.segment_minutes)}
            onChange={(v) => patchContainer({ segment_minutes: Number(v) === 10 ? 10 : 5 })}
          >
            <option value="5">Mỗi 5 phút</option>
            <option value="10">Mỗi 10 phút</option>
          </Select>
        </Row>

        {/* Audio multi-track toggles (§11) — mic & system là 2 track MKV riêng */}
        <Row label="Microphone (track riêng)">
          <Toggle
            checked={profile.audio.microphone.enabled}
            onChange={(next) =>
              patchAudio({ microphone: { ...profile.audio.microphone, enabled: next } })
            }
          />
        </Row>
        <Row label="System Audio (track riêng)">
          <Toggle
            checked={profile.audio.system.enabled}
            onChange={(next) =>
              patchAudio({ system: { ...profile.audio.system, enabled: next } })
            }
          />
        </Row>

        {/* Đường dẫn lưu */}
        <Row label="Đường dẫn lưu">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: 'rgba(15, 23, 42, 0.8)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '6px',
              padding: '4px 8px',
              maxWidth: '180px',
              cursor: 'pointer',
            }}
            onClick={onOpenSettings}
          >
            <span
              style={{
                color: '#f8fafc',
                fontSize: '11px',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={savePath}
            >
              {savePath}
            </span>
            <Folder size={13} color="#60a5fa" style={{ flexShrink: 0 }} />
          </div>
        </Row>
      </div>

      {/* Bottom Status Indicators — real probe state, never a fake thermometer */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingTop: '10px',
          borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          fontSize: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {nvencReady ? (
            <>
              <CheckCircle size={14} color="#4ade80" />
              <span style={{ color: '#94a3b8' }}>NVENC</span>
              <span
                style={{
                  padding: '2px 8px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(34, 197, 94, 0.15)',
                  color: '#4ade80',
                  fontWeight: 600,
                  fontSize: '11px',
                }}
              >
                Sẵn sàng
              </span>
            </>
          ) : (
            <>
              <ShieldAlert size={14} color="#f87171" />
              <span style={{ color: '#94a3b8' }}>NVENC</span>
              <span
                style={{
                  padding: '2px 8px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  color: '#f87171',
                  fontWeight: 600,
                  fontSize: '11px',
                }}
              >
                Không khả dụng
              </span>
            </>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <CheckCircle size={14} color={nvencReady ? '#4ade80' : '#94a3b8'} />
          <span style={{ color: '#94a3b8' }}>Master container</span>
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: 'rgba(59, 130, 246, 0.15)',
              color: '#60a5fa',
              fontWeight: 600,
              fontSize: '11px',
            }}
          >
            MKV
          </span>
        </div>
      </div>
    </div>
  );
};

// ─── Small presentational helpers ────────────────────────────────────────────

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
    <span style={{ color: '#94a3b8' }}>{label}</span>
    {children}
  </div>
);

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  children: React.ReactNode;
}

const Select: React.FC<SelectProps> = ({ value, onChange, disabled, children }) => (
  <div style={{ position: 'relative' }}>
    <select
      value={value}
      disabled={disabled ?? false}
      onChange={(e) => onChange(e.target.value)}
      style={{
        appearance: 'none',
        backgroundColor: 'rgba(15, 23, 42, 0.8)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '6px',
        color: '#f8fafc',
        padding: '4px 24px 4px 10px',
        fontSize: '12px',
        fontWeight: 600,
        cursor: disabled ? 'not-allowed' : 'pointer',
        outline: 'none',
        opacity: disabled ? 0.55 : 1,
      }}
    >
      {children}
    </select>
    <ChevronDown
      size={12}
      color="#94a3b8"
      style={{
        position: 'absolute',
        right: '6px',
        top: '50%',
        transform: 'translateY(-50%)',
        pointerEvents: 'none',
      }}
    />
  </div>
);

const Toggle: React.FC<{ checked: boolean; onChange: (next: boolean) => void }> = ({
  checked,
  onChange,
}) => (
  <button
    onClick={() => onChange(!checked)}
    role="switch"
    aria-checked={checked}
    style={{
      width: '32px',
      height: '18px',
      borderRadius: '9999px',
      backgroundColor: checked ? '#3b82f6' : '#334155',
      position: 'relative',
      border: 'none',
      cursor: 'pointer',
      padding: 0,
      transition: 'background-color 0.2s',
    }}
  >
    <span
      style={{
        position: 'absolute',
        top: '2px',
        left: checked ? '16px' : '2px',
        width: '14px',
        height: '14px',
        borderRadius: '50%',
        backgroundColor: '#ffffff',
        transition: 'left 0.2s',
      }}
    />
  </button>
);
