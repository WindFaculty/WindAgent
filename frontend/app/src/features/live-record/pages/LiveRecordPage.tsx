import React from 'react';
import { Video, Play, Pause, Square, Settings } from 'lucide-react';
import { useLiveRecord } from '../hooks/useLiveRecord';
import { LiveVideoPreview } from '../components/LiveVideoPreview';
import { RecordingStatusPanel } from '../components/RecordingStatusPanel';
import { DeviceSettingsPanel } from '../components/DeviceSettingsPanel';
import { AudioMonitoringPanel } from '../components/AudioMonitoringPanel';
import { SceneListPanel } from '../components/SceneListPanel';
import { TeleprompterPanel } from '../components/TeleprompterPanel';
import { RecentRecordingsPanel } from '../components/RecentRecordingsPanel';
import { LiveMetricCards } from '../components/LiveMetricCards';
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
          {/* Button 1: Bắt đầu ghi / Dừng ghi */}
          <button
            onClick={handleStartRecording}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 20px',
              borderRadius: '8px',
              backgroundColor: isRecording ? '#2563eb' : '#3b82f6',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: '#ffffff',
              fontSize: '13px',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: isRecording
                ? '0 0 16px rgba(37, 99, 235, 0.5)'
                : '0 4px 12px rgba(59, 130, 246, 0.3)',
              transition: 'all 0.2s ease',
            }}
          >
            <span
              style={{
                display: 'inline-block',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: '#ffffff',
              }}
            />
            <span>{isRecording ? 'Bắt đầu ghi' : 'Bắt đầu ghi'}</span>
          </button>

          {/* Button 2: Tạm dừng */}
          <button
            onClick={handlePauseRecording}
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
            onClick={handleStopRecording}
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
          isRecording={isRecording}
          recordingTimeFormatted={recordingTimeFormatted}
          resolution={resolution}
          fps={fps}
          activeSceneIndex={activeSceneIndex}
          teleprompterText={teleprompterText}
        />
        <RecordingStatusPanel
          isRecording={isRecording}
          recordingTimeFormatted={recordingTimeFormatted}
          recordedFrames={recordedFrames}
          droppedFrames={droppedFrames}
          droppedFramesPercent={droppedFramesPercent}
          storageUsedGB={storageUsedGB}
          currentBitrate={currentBitrate}
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

      {/* Bottom Row: 6 Metric Cards */}
      <LiveMetricCards
        recordingTimeFormatted={recordingTimeFormatted}
        isRecording={isRecording}
        droppedFrames={droppedFrames}
        droppedFramesPercent={droppedFramesPercent}
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
