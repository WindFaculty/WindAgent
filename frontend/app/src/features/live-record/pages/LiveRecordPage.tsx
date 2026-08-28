import React, { useMemo } from 'react';
import { Video, Play, Pause, Square, Settings, ShieldAlert } from 'lucide-react';
import { useLiveRecordingController } from '../hooks/useLiveRecordingController';
import { LiveVideoPreview } from '../components/LiveVideoPreview';
import { RecordingStatusPanel } from '../components/RecordingStatusPanel';
import { DeviceSettingsPanel } from '../components/DeviceSettingsPanel';
import { AudioMonitoringPanel } from '../components/AudioMonitoringPanel';
import { SceneListPanel } from '../components/SceneListPanel';
import { TeleprompterPanel } from '../components/TeleprompterPanel';
import { RecentRecordingsPanel } from '../components/RecentRecordingsPanel';
import { LiveMetricCards } from '../components/LiveMetricCards';
import { DirectorPanel } from '../components/DirectorPanel';
import { PreflightChecklist } from '../components/PreflightChecklist';
import { SettingsModal, AddSceneModal, PlaybackModal } from '../components/RecordModals';

/**
 * LiveRecordPage — Phase 14 cutover (ban_ke_hoach_v1.md §18): this component
 * RENDERS ONLY. Orchestration lives in `useLiveRecordingController`
 * (session · director · plan · preflight · Take API); the legacy mock hook is
 * no longer a production metrics authority here.
 */
export const LiveRecordPage: React.FC = () => {
  const ctl = useLiveRecordingController();
  const ui = ctl.ui;

  // Derived render values — pure projections of controller state.
  const effectiveIsRecording = ctl.metrics.isRecording;
  const isPaused = ctl.metrics.isPaused;
  const previewDataUrl = ctl.previewFrame?.jpeg_base64
    ? `data:image/jpeg;base64,${ctl.previewFrame.jpeg_base64}`
    : undefined;
  const effectiveTeleprompterText = ctl.planMode ? '' : ui.teleprompterText;
  const planTeleprompterText = ctl.projectedScenes[ui.activeSceneIndex]?.script ?? '';

  // Bytes written for THIS take come from real segment events the engine
  // emitted (§16 manifest relay) — no fake storage counter exists anymore.
  const storageUsedGB = useMemo<number | null>(() => {
    if (!ctl.native) return ui.storageUsedGB > 0 ? ui.storageUsedGB : null;
    if (ctl.segments.length === 0) return null;
    return ctl.segments.reduce((acc, s) => acc + s.byte_len, 0) / 1_000_000_000;
  }, [ctl.native, ctl.segments, ui.storageUsedGB]);

  return (
    <div
      style={{
        padding: '24px 32px',
        maxWidth: '1680px',
        margin: '0 auto',
        minHeight: '100%',
        color: '#f8fafc',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px',
      }}
      data-testid="canonical-live-record-page"
    >
      {/* Page Header Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        {/* Title & Icon */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '12px',
              backgroundColor: 'rgba(37, 99, 235, 0.2)',
              border: '1px solid rgba(59, 130, 246, 0.4)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 16px rgba(59, 130, 246, 0.25)',
            }}
          >
            <Video size={22} color="#60a5fa" />
          </div>
          <div>
            <h1
              style={{
                margin: '0 0 4px 0',
                fontSize: '22px',
                fontWeight: 800,
                letterSpacing: '-0.3px',
                color: '#ffffff',
              }}
            >
              Live Record Video
            </h1>
            <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8' }}>
              Ghi hình trực tiếp chất lượng cao cho sản xuất nội dung và phát sóng.
            </p>
          </div>
        </div>

        {/* Action Button Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Button 1: Bắt đầu ghi — native đi qua preflight + Director READY (§20) */}
          <button
            onClick={() => void ctl.startTake()}
            disabled={ctl.native && (!ctl.allPreflightPass || effectiveIsRecording || ctl.startInFlight)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 20px',
              borderRadius: '8px',
              backgroundColor:
                ctl.native && !ctl.allPreflightPass ? '#334155' : effectiveIsRecording ? '#2563eb' : '#3b82f6',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: '#ffffff',
              fontSize: '13px',
              fontWeight: 700,
              cursor:
                ctl.native && (!ctl.allPreflightPass || effectiveIsRecording || ctl.startInFlight)
                  ? 'not-allowed'
                  : 'pointer',
              opacity: ctl.native && !ctl.allPreflightPass ? 0.6 : 1,
              boxShadow: effectiveIsRecording
                ? '0 0 16px rgba(37, 99, 235, 0.5)'
                : '0 4px 12px rgba(59, 130, 246, 0.3)',
              transition: 'all 0.2s ease',
            }}
            title={
              ctl.native && !ctl.allPreflightPass
                ? 'Preflight chưa PASS — xem checklist bên dưới'
                : undefined
            }
          >
            <span
              style={{
                display: 'inline-block',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: effectiveIsRecording ? '#f87171' : '#ffffff',
              }}
            />
            <span>
              {ctl.startInFlight
                ? 'Đang khởi động…'
                : effectiveIsRecording
                  ? 'Đang ghi'
                  : 'Bắt đầu ghi'}
            </span>
          </button>

          {/* Button 2: Tạm dừng */}
          <button
            onClick={() => void (isPaused ? ctl.resumeTake() : ctl.pauseTake())}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 18px',
              borderRadius: '8px',
              backgroundColor: '#d97706',
              border: 'none',
              color: '#ffffff',
              fontSize: '13px',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(217, 119, 6, 0.3)',
              transition: 'all 0.2s ease',
            }}
          >
            {isPaused ? <Play size={15} /> : <Pause size={15} />}
            <span>{isPaused ? 'Tiếp tục' : 'Tạm dừng'}</span>
          </button>

          {/* Button 3: Kết thúc */}
          <button
            onClick={() => void ctl.stopTake()}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 18px',
              borderRadius: '8px',
              backgroundColor: '#dc2626',
              border: 'none',
              color: '#ffffff',
              fontSize: '13px',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(220, 38, 38, 0.3)',
              transition: 'all 0.2s ease',
            }}
          >
            <Square size={14} fill="#ffffff" />
            <span>Kết thúc</span>
          </button>

          {/* Button 4: Cài đặt */}
          <button
            onClick={() => ui.setIsSettingsOpen(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 16px',
              borderRadius: '8px',
              backgroundColor: 'rgba(15, 23, 42, 0.8)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              color: '#e2e8f0',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
          >
            <Settings size={15} />
            <span>Cài đặt</span>
          </button>
        </div>
      </div>

      {/* Start-refusal banner (§20: director not READY ⇒ START refused) */}
      {ctl.lastStartError !== null && (
        <div
          data-testid="start-refusal-banner"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 14px',
            borderRadius: '10px',
            backgroundColor: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.45)',
            color: '#fca5a5',
            fontSize: '12px',
            fontWeight: 600,
          }}
        >
          <ShieldAlert size={15} />
          {ctl.lastStartError}
        </div>
      )}

      {/* Top Row: 3 Panels */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1.8fr) minmax(0, 1fr) minmax(0, 1fr)',
          gap: '20px',
          alignItems: 'stretch',
        }}
      >
        <LiveVideoPreview
          isRecording={effectiveIsRecording}
          recordingTimeFormatted={ctl.metrics.timeFormatted}
          resolution={ui.resolution}
          fps={ui.fps}
          activeSceneIndex={ui.activeSceneIndex}
          teleprompterText={ctl.planMode ? planTeleprompterText : effectiveTeleprompterText}
          previewDataUrl={previewDataUrl}
        />
        <RecordingStatusPanel
          isRecording={effectiveIsRecording}
          recordingTimeFormatted={ctl.metrics.timeFormatted}
          recordedFrames={ctl.metrics.framesCaptured}
          droppedFrames={ctl.metrics.framesDropped}
          droppedFramesPercent={ctl.metrics.droppedPct}
          storageUsedGB={storageUsedGB}
          currentBitrate={ctl.metrics.bitrateMbps}
          captureFps={ctl.metrics.captureFps ?? undefined}
          encodeFps={ctl.metrics.encodeFps ?? undefined}
          avSyncErrorMs={ctl.metrics.avSyncErrorMs ?? undefined}
          resourceStage={ctl.metrics.resourceStage ?? undefined}
        />
        <DeviceSettingsPanel
          profile={ctl.engineProfile}
          onProfileChange={ctl.setEngineProfile}
          sources={ctl.captureSources}
          nvencReady={Boolean(ctl.capabilities?.nvenc_available)}
          savePath={ui.savePath}
          onOpenSettings={() => ui.setIsSettingsOpen(true)}
        />
      </div>

      {/* Middle Row: 4 Panels */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1.1fr) minmax(0, 1.3fr) minmax(0, 1.4fr) minmax(0, 1.3fr)',
          gap: '20px',
          alignItems: 'stretch',
          minHeight: '280px',
        }}
      >
        <AudioMonitoringPanel
          audioLevels={ctl.audioLevels}
          toggleMicMute={ctl.toggleMicMute}
          toggleSystemMute={ctl.toggleSystemMute}
          toggleVoiceoverMute={ui.toggleVoiceoverMute}
          onOpenSettings={() => ui.setIsSettingsOpen(true)}
        />
        <SceneListPanel
          scenes={[...ctl.projectedScenes]}
          activeSceneIndex={ui.activeSceneIndex}
          onSelectScene={ui.handleSelectScene}
          onOpenAddScene={() => ui.setIsAddSceneOpen(true)}
          totalExpectedDurationFormatted={ctl.totalExpectedDurationFormatted}
        />
        <TeleprompterPanel
          text={ctl.planMode ? planTeleprompterText : effectiveTeleprompterText}
          fontSize={ui.teleprompterFontSize}
          setFontSize={ui.setTeleprompterFontSize}
          isAutoScroll={ui.isAutoScroll}
          setIsAutoScroll={ui.setIsAutoScroll}
          scrollSpeed={ui.scrollSpeed}
          setScrollSpeed={ui.setScrollSpeed}
        />
        <RecentRecordingsPanel
          recordings={ui.recordings}
          onSelectPlayback={(rec) => ui.setSelectedPlayback(rec)}
          onViewAll={() => ui.setSelectedPlayback(ui.recordings[0])}
        />
      </div>

      {/* Director & Preflight — real engine wiring (desktop shell only) */}
      {ctl.native && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)',
            gap: '20px',
            alignItems: 'stretch',
          }}
          data-testid="director-preflight-row"
        >
          <DirectorPanel
            connectionState={ctl.director.connectionState}
            currentSceneId={ctl.director.currentSceneId}
            currentCueId={ctl.director.currentCueId}
            latestModelTurn={ctl.director.latestModelTurn}
            lastToolResult={ctl.director.lastToolResult}
            allowedTools={[...ctl.director.allowedTools]}
          />
          <PreflightChecklist checks={ctl.preflightChecks} />
        </div>
      )}

      {/* Bottom Row: 6 Metric Cards — §18 engine-authoritative telemetry */}
      <LiveMetricCards
        recordingTimeFormatted={ctl.metrics.timeFormatted}
        isRecording={effectiveIsRecording}
        droppedFrames={ctl.metrics.framesDropped}
        droppedFramesPercent={ctl.metrics.droppedPct}
        metrics={ctl.metrics}
      />

      {/* Modals & Dialogs */}
      <SettingsModal
        isOpen={ui.isSettingsOpen}
        onClose={() => ui.setIsSettingsOpen(false)}
        savePath={ui.savePath}
        setSavePath={ui.setSavePath}
      />

      <AddSceneModal
        isOpen={ui.isAddSceneOpen}
        onClose={() => ui.setIsAddSceneOpen(false)}
        onAddScene={ui.handleAddScene}
      />

      <PlaybackModal recording={ui.selectedPlayback} onClose={() => ui.setSelectedPlayback(null)} />
    </div>
  );
};

export default LiveRecordPage;
