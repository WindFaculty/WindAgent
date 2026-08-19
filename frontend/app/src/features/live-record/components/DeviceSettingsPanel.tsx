import React from 'react';
import { ChevronDown, Folder, CheckCircle, Thermometer } from 'lucide-react';

export interface DeviceSettingsPanelProps {
  cameraSource: string;
  setCameraSource: (val: string) => void;
  micSource: string;
  setMicSource: (val: string) => void;
  resolution: string;
  setResolution: (val: string) => void;
  fps: number;
  setFps: (val: number) => void;
  bitrate: string;
  setBitrate: (val: string) => void;
  format: string;
  setFormat: (val: string) => void;
  savePath: string;
  setSavePath?: (val: string) => void;
  autoSplit: boolean;
  setAutoSplit: (val: boolean | ((prev: boolean) => boolean)) => void;
  deviceTemp: number;
  onOpenSettings: () => void;
}

export const DeviceSettingsPanel: React.FC<DeviceSettingsPanelProps> = ({
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
  autoSplit,
  setAutoSplit,
  deviceTemp,
  onOpenSettings,
}) => {
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
            Cài Đặt Thiết Bị & Ghi Hình
          </h3>
          <span style={{ fontSize: '11px', color: '#94a3b8' }}>Cấu hình: Mặc định Studio</span>
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

      {/* Settings Grid / Fields */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
        {/* Nguồn Camera / Màn hình AI */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#94a3b8' }}>Nguồn Màn hình / Camera</span>
          <div style={{ position: 'relative' }}>
            <select
              value={cameraSource}
              onChange={(e) => setCameraSource(e.target.value)}
              style={{
                appearance: 'none',
                backgroundColor: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                color: '#f8fafc',
                padding: '4px 24px 4px 10px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <option value="Sony A7 IV (USB)">Sony A7 IV (USB)</option>
              <option value="AI Agent Live Screen">AI Agent Live Screen</option>
              <option value="AI Code Studio & Terminal">AI Code Studio & Terminal</option>
              <option value="Autonomous Browser Capture">Autonomous Browser Capture</option>
              <option value="Agent Swarm Pipeline Flow">Agent Swarm Pipeline Flow</option>
              <option value="OBS Virtual Camera">OBS Virtual Camera</option>
            </select>
            <ChevronDown
              size={12}
              color="#94a3b8"
              style={{ position: 'absolute', right: '6px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
            />
          </div>
        </div>

        {/* Nguồn Micro / Âm thanh */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#94a3b8' }}>Nguồn Âm thanh / Mic</span>
          <div style={{ position: 'relative' }}>
            <select
              value={micSource}
              onChange={(e) => setMicSource(e.target.value)}
              style={{
                appearance: 'none',
                backgroundColor: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                color: '#f8fafc',
                padding: '4px 24px 4px 10px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <option value="Shure MV7+ (USB)">Shure MV7+ (USB)</option>
              <option value="AI Voiceover (Edge TTS)">AI Voiceover (Edge TTS)</option>
              <option value="AI Voiceover (ElevenLabs)">AI Voiceover (ElevenLabs)</option>
              <option value="System Audio Loopback">System Audio Loopback</option>
              <option value="Rode Wireless GO II">Rode Wireless GO II</option>
            </select>
            <ChevronDown
              size={12}
              color="#94a3b8"
              style={{ position: 'absolute', right: '6px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
            />
          </div>
        </div>

        {/* Độ phân giải */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#94a3b8' }}>Độ phân giải</span>
          <div style={{ position: 'relative' }}>
            <select
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              style={{
                appearance: 'none',
                backgroundColor: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                color: '#f8fafc',
                padding: '4px 24px 4px 10px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <option value="1920 x 1080 (Full HD)">1920 x 1080 (Full HD)</option>
              <option value="3840 x 2160 (4K UHD)">3840 x 2160 (4K UHD)</option>
              <option value="1280 x 720 (HD)">1280 x 720 (HD)</option>
            </select>
            <ChevronDown
              size={12}
              color="#94a3b8"
              style={{ position: 'absolute', right: '6px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
            />
          </div>
        </div>

        {/* FPS */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#94a3b8' }}>FPS</span>
          <div style={{ position: 'relative' }}>
            <select
              value={fps}
              onChange={(e) => setFps(Number(e.target.value))}
              style={{
                appearance: 'none',
                backgroundColor: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                color: '#f8fafc',
                padding: '4px 24px 4px 10px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <option value={60}>60</option>
              <option value={30}>30</option>
              <option value={24}>24</option>
            </select>
            <ChevronDown
              size={12}
              color="#94a3b8"
              style={{ position: 'absolute', right: '6px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
            />
          </div>
        </div>

        {/* Bitrate */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#94a3b8' }}>Bitrate</span>
          <div style={{ position: 'relative' }}>
            <select
              value={bitrate}
              onChange={(e) => setBitrate(e.target.value)}
              style={{
                appearance: 'none',
                backgroundColor: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                color: '#f8fafc',
                padding: '4px 24px 4px 10px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <option value="20 Mbps">20 Mbps</option>
              <option value="50 Mbps">50 Mbps</option>
              <option value="12 Mbps">12 Mbps</option>
              <option value="8 Mbps">8 Mbps</option>
            </select>
            <ChevronDown
              size={12}
              color="#94a3b8"
              style={{ position: 'absolute', right: '6px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
            />
          </div>
        </div>

        {/* Định dạng */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#94a3b8' }}>Định dạng</span>
          <div style={{ position: 'relative' }}>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              style={{
                appearance: 'none',
                backgroundColor: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                color: '#f8fafc',
                padding: '4px 24px 4px 10px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <option value="MP4 (H.264)">MP4 (H.264)</option>
              <option value="MP4 (HEVC)">MP4 (HEVC)</option>
              <option value="MKV">MKV</option>
              <option value="ProRes">ProRes</option>
            </select>
            <ChevronDown
              size={12}
              color="#94a3b8"
              style={{ position: 'absolute', right: '6px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
            />
          </div>
        </div>

        {/* Đường dẫn lưu */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#94a3b8' }}>Đường dẫn lưu</span>
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
            }}
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
            <Folder size={13} color="#60a5fa" style={{ flexShrink: 0, cursor: 'pointer' }} />
          </div>
        </div>

        {/* Tự động chia file */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#94a3b8' }}>Tự động chia file</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ color: '#cbd5e1', fontSize: '11px' }}>30 phút</span>
            <button
              onClick={() => setAutoSplit((prev) => !prev)}
              style={{
                width: '32px',
                height: '18px',
                borderRadius: '9999px',
                backgroundColor: autoSplit ? '#3b82f6' : '#334155',
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
                  left: autoSplit ? '16px' : '2px',
                  width: '14px',
                  height: '14px',
                  borderRadius: '50%',
                  backgroundColor: '#ffffff',
                  transition: 'left 0.2s',
                }}
              />
            </button>
          </div>
        </div>
      </div>

      {/* Bottom Status Indicators */}
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
          <CheckCircle size={14} color="#4ade80" />
          <span style={{ color: '#94a3b8' }}>Kết nối thiết bị</span>
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
            Tốt
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Thermometer size={14} color="#fbbf24" />
          <span style={{ color: '#94a3b8' }}>Nhiệt độ thiết bị</span>
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: 'rgba(234, 179, 8, 0.15)',
              color: '#facc15',
              fontWeight: 600,
              fontSize: '11px',
            }}
          >
            {deviceTemp}°C
          </span>
        </div>
      </div>
    </div>
  );
};
