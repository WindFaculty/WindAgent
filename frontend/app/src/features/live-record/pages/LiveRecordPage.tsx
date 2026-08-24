import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Video, Play, Pause, Square, Settings, Bot } from 'lucide-react';
import { useLiveRecord, formatDuration } from '../hooks/useLiveRecord';
import { useLiveRecorderSession } from '../hooks/useLiveRecorderSession';
import { useLiveDirectorPlan } from '../hooks/useLiveDirectorPlan';
import { useLiveDirector } from '../hooks/useLiveDirector';
import { useApiClient } from '../../../api/ApiProvider';
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

export const LiveRecordPage: React.FC = () => {
  const {
    isRecording,
    isPaused,
    recordingTimeFormatted,
    recordedFrames,
    droppedFrames,
    droppedFramesPercent,
    storageUsedGB,
    currentBitrate,
    cameraSource,
    setCameraSource,
    micSource,
    setMicSource,
    resolution,
    setResolution,
    fps,
    setFps,
    bitrate,
    setBitrate,
    format,
    setFormat,
    savePath,
    setSavePath,
    autoSplit,
    setAutoSplit,
    deviceTemp,
    audioLevels,
    scenes,
    activeSceneIndex,
    totalExpectedDurationFormatted,
    teleprompterFontSize,
    setTeleprompterFontSize,
    isAutoScroll,
    setIsAutoScroll,
    scrollSpeed,
    setScrollSpeed,
    teleprompterText,
    recordings,
    isSettingsOpen,
    setIsSettingsOpen,
    isAddSceneOpen,
    setIsAddSceneOpen,
    selectedPlayback,
    setSelectedPlayback,
    handleStartRecording,
    handlePauseRecording,
    handleStopRecording,
    handleSelectScene,
    handleAddScene,
    toggleMicMute,
    toggleSystemMute,
    toggleVoiceoverMute,
  } = useLiveRecord();

  // ── Phase E/F cutover — frozen plan + real engine state override the mock ──
  const apiClient = useApiClient();
  const planLoader = useLiveDirectorPlan();
  const plan = planLoader.plan;
  const planScenes = plan?.scenes ?? [];
  // Plan mode drives Scene List / teleprompter from the FROZEN plan (Section 20);
  // without a plan (fresh web/dev session) the page keeps the legacy mock store.
  const planMode = planScenes.length > 0;
  const [activePosition, setActivePosition] = useState(0);
  const [isStartingEngine, setIsStartingEngine] = useState(false);

  // Take lineage: createTake before engine start → segments relay into the DB.
  const takeIdRef = useRef<string | null>(null);
  const relaySegment = useCallback(
    (seg: { segment_index: number; file_token: string; started_at: string; ended_at?: string; is_playable: boolean }) => {
      const takeId = takeIdRef.current;
      if (!takeId) return;
      void apiClient.liveRecord
        .recordTakeSegment(takeId, {
          segment_index: seg.segment_index,
          file_token: seg.file_token,
          started_at: seg.started_at ?? null,
          ended_at: seg.ended_at ?? null,
          is_playable: seg.is_playable,
        })
        .catch(() => { /* lineage relay is best-effort — recording continues */ });
    },
    [apiClient],
  );

  const recorder = useLiveRecorderSession({ onSegmentEvent: relaySegment });
  const director = useLiveDirector({
    plan,
    previewFrame: recorder.previewFrame,
    takeId: takeIdRef.current,
    onPauseRecording: async () => { await recorder.pause(); },
    onResumeRecording: async () => { await recorder.resume(); },
    onCreateMarker: async (markerType) => { await recorder.createMarker({ marker_type: markerType }); },
  });
  const rs = recorder.status;
  const effectiveIsRecording = rs ? rs.state === 'RECORDING' : isRecording;
  const effectivePaused = rs ? rs.state === 'PAUSED' : isPaused;
  const effectiveTimeFormatted = rs ? formatDuration(rs.elapsed_sec) : recordingTimeFormatted;
  const effectiveFrames = rs ? rs.frames_captured : recordedFrames;
  const effectiveDropped = rs ? rs.frames_dropped : droppedFrames;
  const effectiveDroppedPct = rs
    ? (rs.dropped_pct.toFixed(2))
    : droppedFramesPercent;
  const effectiveBitrate = rs && rs.bitrate_mbps > 0 ? rs.bitrate_mbps : currentBitrate;
  const previewDataUrl = recorder.previewFrame?.jpeg_base64
    ? `data:image/jpeg;base64,${recorder.previewFrame.jpeg_base64}`
    : undefined;

  // Preflight inputs from the real capability probe; unknown guards stay
  // optimistic and are re-blocked via the engine's own blockers list.
  const caps = recorder.capabilities;
  const blockerCodes = new Set<string>([
    ...((caps?.blockers as readonly string[] | undefined) ?? []),
    ...((rs?.blockers as readonly string[] | undefined) ?? []),
  ]);

  // §23/§33: privacy scan runs once per loaded plan (fail-closed until PASS).
  const [privacyScan, setPrivacyScan] = useState<{ status: string } | null>(null);
  const scannedPlanIdRef = useRef<string | null>(null);
  useEffect(() => {
    const planId = planMode && plan ? plan.id : null;
    if (!planId || !recorder.native) return;
    if (scannedPlanIdRef.current === planId) return;
    scannedPlanIdRef.current = planId;
    setPrivacyScan(null);
    let cancelled = false;
    apiClient.liveRecord
      .runPrivacyScan(planId)
      .then((res) => {
        if (!cancelled) setPrivacyScan({ status: String(res['status'] ?? 'BLOCKED') });
      })
      .catch(() => {
        if (!cancelled) setPrivacyScan({ status: 'BLOCKED' }); // scan unavailable ⇒ fail-closed
      });
    return () => {
      cancelled = true;
    };
  }, [plan, planMode, recorder.native, apiClient]);

  const preflightChecks = {
    episodeRevisionOk: !blockerCodes.has('PLAN_STALE'),
    planFrozen: !blockerCodes.has('PLAN_NOT_FROZEN'),
    planStale: blockerCodes.has('PLAN_STALE'),
    workspaceHashOk: !blockerCodes.has('WORKSPACE_HASH_MISMATCH'),
    artifactsPresent: !blockerCodes.has('ARTIFACT_MISSING'),
    actionsUntampered: !blockerCodes.has('ACTION_TAMPERED'),
    providerResolved: !blockerCodes.has('PROVIDER_UNAVAILABLE'),
    credentialValid: !blockerCodes.has('CREDENTIAL_INVALID'),
    liveConnectivityOk: !blockerCodes.has('LIVE_CONNECTIVITY_FAILED'),
    privacyScanPassed: recorder.native ? privacyScan?.status === 'PASS' : true,
    recorderHealthy:
      recorder.native &&
      !blockerCodes.has('RECORDER_SIDECAR_UNHEALTHY') &&
      !(caps !== null && caps.engine_available === false),
    wgcAvailable: Boolean(caps?.wgc_available ?? false),
    nvencAvailable: Boolean(caps?.nvenc_available ?? false),
    diskSufficient: caps ? Number(caps.disk_free_gb) >= 2 : false,
    outputWritable: Boolean(caps?.output_writable ?? false),
  };

  // Section 23: nút "Bắt đầu ghi" chỉ enable khi preflight PASS hết (native).
  const recordingHardChecks = {
    episodeRevisionOk: preflightChecks.episodeRevisionOk,
    planFrozen: planMode ? planLoader.plan?.status === 'FROZEN' : preflightChecks.planFrozen,
    workspaceHashOk: preflightChecks.workspaceHashOk,
    artifactsPresent: preflightChecks.artifactsPresent,
    actionsUntampered: preflightChecks.actionsUntampered,
    providerResolved: preflightChecks.providerResolved,
    credentialValid: preflightChecks.credentialValid,
    liveConnectivityOk: preflightChecks.liveConnectivityOk,
    privacyScanPassed: preflightChecks.privacyScanPassed,
    recorderHealthy: preflightChecks.recorderHealthy,
    wgcAvailable: preflightChecks.wgcAvailable,
    nvencAvailable: preflightChecks.nvencAvailable,
    diskSufficient: preflightChecks.diskSufficient,
    outputWritable: preflightChecks.outputWritable,
  };
  const allPreflightPass = Object.values(recordingHardChecks).every(Boolean);

  // Native Start flow (Section 22-23): createTake (lineage) → prepare → start.
  const handleNativeStart = async (): Promise<void> => {
    if (!recorder.native || isStartingEngine || effectiveIsRecording) return;
    setIsStartingEngine(true);
    try {
      // 1. Lineage: open the take in the API so segments/events have a home.
      if (plan && !takeIdRef.current) {
        try {
          const take = await apiClient.liveRecord.createTake(plan.id, {});
          const tid = String(take['take_id'] ?? take['id'] ?? '');
          if (tid) takeIdRef.current = tid;
        } catch {
          // API unavailable → engine generates its own take id; lineage relay
          // is skipped for this run (recorded as a warning by the sidecar path).
        }
      }
      // 2. Prepare the sidecar with the frozen profile.
      const profile = plan?.recording_profile;
      const prepared = (await recorder.prepare({
        execution_plan_id: plan?.id ?? 'adhoc',
        execution_plan_hash: plan?.plan_hash ?? '',
        episode_id: plan?.episode_id ?? '',
        output_dir: savePath || 'recordings',
        profile: {
          resolution: (profile?.resolution as string) ?? '1920x1080',
          fps: profile?.fps ?? 60,
          codec: profile?.codec ?? 'H264',
          segment_minutes: profile?.segment_minutes ?? 5,
          audio_enabled: false,
        },
      })) as { prepared?: boolean; blockers?: string[] } | null;
      if (prepared && prepared.prepared === false) return; // blockers surfaced via events
      // 3. Start — empty take_id lets the engine mint one when no API take exists.
      await recorder.start({
        execution_plan_id: plan?.id ?? 'adhoc',
        ...(takeIdRef.current ? { take_id: takeIdRef.current } : {}),
      });
    } finally {
      setIsStartingEngine(false);
    }
  };

  const handleStopClick = async (): Promise<void> => {
    if (recorder.native) {
      await recorder.stop();
      takeIdRef.current = null;
    } else {
      handleStopRecording();
    }
  };

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
          {/* Button 1: Bắt đầu ghi — native đi qua preflight + engine thật */}
          <button
            onClick={() => void (recorder.native ? handleNativeStart() : handleStartRecording())}
            disabled={
              recorder.native &&
              (!allPreflightPass || effectiveIsRecording || isStartingEngine)
            }
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 20px',
              borderRadius: '8px',
              backgroundColor:
                recorder.native && !allPreflightPass ? '#334155' : effectiveIsRecording ? '#2563eb' : '#3b82f6',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: '#ffffff',
              fontSize: '13px',
              fontWeight: 700,
              cursor:
                recorder.native && (!allPreflightPass || effectiveIsRecording || isStartingEngine)
                  ? 'not-allowed'
                  : 'pointer',
              opacity: recorder.native && !allPreflightPass ? 0.6 : 1,
              boxShadow: effectiveIsRecording
                ? '0 0 16px rgba(37, 99, 235, 0.5)'
                : '0 4px 12px rgba(59, 130, 246, 0.3)',
              transition: 'all 0.2s ease',
            }}
            title={
              recorder.native && !allPreflightPass
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
              {isStartingEngine
                ? 'Đang khởi động…'
                : effectiveIsRecording
                  ? 'Đang ghi'
                  : 'Bắt đầu ghi'}
            </span>
          </button>

          {/* Button 2: Tạm dừng */}
          <button
            onClick={() => (recorder.native ? void recorder.pause() : handlePauseRecording())}
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
            onClick={() => void handleStopClick()}
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
            onClick={() => setIsSettingsOpen(true)}
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
          recordingTimeFormatted={effectiveTimeFormatted}
          resolution={resolution}
          fps={fps}
          activeSceneIndex={activeSceneIndex}
          teleprompterText={teleprompterText}
          previewDataUrl={previewDataUrl}
        />
        <RecordingStatusPanel
          isRecording={effectiveIsRecording}
          recordingTimeFormatted={effectiveTimeFormatted}
          recordedFrames={effectiveFrames}
          droppedFrames={effectiveDropped}
          droppedFramesPercent={effectiveDroppedPct}
          storageUsedGB={storageUsedGB}
          currentBitrate={effectiveBitrate}
        />
        <DeviceSettingsPanel
          cameraSource={cameraSource}
          setCameraSource={setCameraSource}
          micSource={micSource}
          setMicSource={setMicSource}
          resolution={resolution}
          setResolution={setResolution}
          fps={fps}
          setFps={setFps}
          bitrate={bitrate}
          setBitrate={setBitrate}
          format={format}
          setFormat={setFormat}
          savePath={savePath}
          setSavePath={setSavePath}
          autoSplit={autoSplit}
          setAutoSplit={setAutoSplit}
          deviceTemp={deviceTemp}
          onOpenSettings={() => setIsSettingsOpen(true)}
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
          audioLevels={audioLevels}
          toggleMicMute={toggleMicMute}
          toggleSystemMute={toggleSystemMute}
          toggleVoiceoverMute={toggleVoiceoverMute}
          onOpenSettings={() => setIsSettingsOpen(true)}
        />
        <SceneListPanel
          scenes={scenes}
          activeSceneIndex={activeSceneIndex}
          onSelectScene={handleSelectScene}
          onOpenAddScene={() => setIsAddSceneOpen(true)}
          totalExpectedDurationFormatted={totalExpectedDurationFormatted}
        />
        <TeleprompterPanel
          text={teleprompterText}
          fontSize={teleprompterFontSize}
          setFontSize={setTeleprompterFontSize}
          isAutoScroll={isAutoScroll}
          setIsAutoScroll={setIsAutoScroll}
          scrollSpeed={scrollSpeed}
          setScrollSpeed={setScrollSpeed}
        />
        <RecentRecordingsPanel
          recordings={recordings}
          onSelectPlayback={(rec) => setSelectedPlayback(rec)}
          onViewAll={() => setSelectedPlayback(recordings[0])}
        />
      </div>

      {/* Director & Preflight — real engine wiring (desktop shell only) */}
      {recorder.native && (
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
            connectionState="DISCONNECTED"
            currentSceneId={`scene ${activeSceneIndex + 1}`}
            currentCueId="—"
            allowedTools={[]}
          />
          <PreflightChecklist checks={preflightChecks} />
        </div>
      )}

      {/* Bottom Row: 6 Metric Cards */}
      <LiveMetricCards
        recordingTimeFormatted={effectiveTimeFormatted}
        isRecording={effectiveIsRecording}
        droppedFrames={effectiveDropped}
        droppedFramesPercent={effectiveDroppedPct}
      />

      {/* Modals & Dialogs */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        savePath={savePath}
        setSavePath={setSavePath}
      />

      <AddSceneModal
        isOpen={isAddSceneOpen}
        onClose={() => setIsAddSceneOpen(false)}
        onAddScene={handleAddScene}
      />

      <PlaybackModal
        recording={selectedPlayback}
        onClose={() => setSelectedPlayback(null)}
      />
    </div>
  );
};

export default LiveRecordPage;
