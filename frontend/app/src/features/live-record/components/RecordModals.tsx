import React, { useState } from 'react';
import { X, Settings, Film } from 'lucide-react';
import type { RecentRecording } from '../hooks/useLiveRecord';

// Settings Modal
export interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  savePath: string;
  setSavePath: (path: string) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  savePath,
  setSavePath,
}) => {
  const [localPath, setLocalPath] = useState(savePath);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '520px',
          backgroundColor: '#0f172a',
          border: '1px solid rgba(59, 130, 246, 0.3)',
          borderRadius: '16px',
          padding: '24px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8)',
          color: '#f8fafc',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Settings size={18} color="#60a5fa" />
            <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>Cài Đặt Studio Live Record</h3>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', fontSize: '13px' }}>
          <div>
            <label style={{ display: 'block', color: '#94a3b8', marginBottom: '6px', fontWeight: 600 }}>
              Thư mục lưu trữ bản ghi
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                value={localPath}
                onChange={(e) => setLocalPath(e.target.value)}
                style={{
                  flex: 1,
                  backgroundColor: '#090d16',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  borderRadius: '6px',
                  padding: '8px 12px',
                  color: '#f8fafc',
                  fontSize: '13px',
                }}
              />
              <button
                onClick={() => {
                  setLocalPath('D:\\WindAgent\\Recordings');
                }}
                style={{
                  padding: '8px 12px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(59, 130, 246, 0.2)',
                  border: '1px solid rgba(59, 130, 246, 0.4)',
                  color: '#60a5fa',
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                Mặc định
              </button>
            </div>
          </div>

          <div>
            <label style={{ display: 'block', color: '#94a3b8', marginBottom: '6px', fontWeight: 600 }}>
              Encoder Phần Cứng
            </label>
            <select
              style={{
                width: '100%',
                backgroundColor: '#090d16',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '6px',
                padding: '8px 12px',
                color: '#f8fafc',
                fontSize: '13px',
              }}
            >
              <option>NVIDIA NVENC H.264 (Phần cứng tăng tốc)</option>
              <option>NVIDIA NVENC HEVC / AV1</option>
              <option>Intel QuickSync Video</option>
              <option>x264 (CPU Software)</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', color: '#94a3b8', marginBottom: '6px', fontWeight: 600 }}>
              Chất lượng Audio Sample Rate
            </label>
            <select
              style={{
                width: '100%',
                backgroundColor: '#090d16',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '6px',
                padding: '8px 12px',
                color: '#f8fafc',
                fontSize: '13px',
              }}
            >
              <option>48 kHz / 24-bit (Chuẩn Studio)</option>
              <option>96 kHz / 24-bit (Hi-Res Audio)</option>
              <option>44.1 kHz / 16-bit (CD Quality)</option>
            </select>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '24px' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              backgroundColor: 'rgba(255, 255, 255, 0.08)',
              border: 'none',
              color: '#cbd5e1',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Hủy
          </button>
          <button
            onClick={() => {
              setSavePath(localPath);
              onClose();
            }}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              backgroundColor: '#3b82f6',
              border: 'none',
              color: '#ffffff',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Lưu thay đổi
          </button>
        </div>
      </div>
    </div>
  );
};

// Add Scene Modal
export interface AddSceneModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAddScene: (title: string, duration: string, script?: string) => void;
}

export const AddSceneModal: React.FC<AddSceneModalProps> = ({ isOpen, onClose, onAddScene }) => {
  const [title, setTitle] = useState('');
  const [duration, setDuration] = useState('00:03:00');
  const [script, setScript] = useState('');

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '480px',
          backgroundColor: '#0f172a',
          border: '1px solid rgba(59, 130, 246, 0.3)',
          borderRadius: '16px',
          padding: '24px',
          color: '#f8fafc',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>Thêm Cảnh Quay Mới</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '13px' }}>
          <div>
            <label style={{ display: 'block', color: '#94a3b8', marginBottom: '6px' }}>Tiêu đề cảnh quay</label>
            <input
              type="text"
              placeholder="VD: Tổng quan kiến trúc Agent Swarm..."
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{
                width: '100%',
                backgroundColor: '#090d16',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '6px',
                padding: '8px 12px',
                color: '#f8fafc',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', color: '#94a3b8', marginBottom: '6px' }}>Thời lượng dự kiến (hh:mm:ss)</label>
            <input
              type="text"
              placeholder="00:03:00"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              style={{
                width: '100%',
                backgroundColor: '#090d16',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '6px',
                padding: '8px 12px',
                color: '#f8fafc',
                fontFamily: 'monospace',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', color: '#94a3b8', marginBottom: '6px' }}>Kịch bản đọc / Teleprompter</label>
            <textarea
              rows={3}
              placeholder="Nhập nội dung MC hoặc diễn giả sẽ nói trong cảnh này..."
              value={script}
              onChange={(e) => setScript(e.target.value)}
              style={{
                width: '100%',
                backgroundColor: '#090d16',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '6px',
                padding: '8px 12px',
                color: '#f8fafc',
                resize: 'vertical',
              }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              backgroundColor: 'rgba(255, 255, 255, 0.08)',
              border: 'none',
              color: '#cbd5e1',
              cursor: 'pointer',
            }}
          >
            Hủy
          </button>
          <button
            onClick={() => {
              if (title.trim()) {
                onAddScene(title.trim(), duration.trim() || '00:02:00', script.trim());
                setTitle('');
                setScript('');
              }
            }}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              backgroundColor: '#3b82f6',
              border: 'none',
              color: '#ffffff',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Thêm cảnh
          </button>
        </div>
      </div>
    </div>
  );
};

// Playback Modal
export interface PlaybackModalProps {
  recording: RecentRecording | null;
  onClose: () => void;
}

export const PlaybackModal: React.FC<PlaybackModalProps> = ({ recording, onClose }) => {
  if (!recording) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.85)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '720px',
          backgroundColor: '#0f172a',
          border: '1px solid rgba(59, 130, 246, 0.3)',
          borderRadius: '16px',
          padding: '24px',
          color: '#f8fafc',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>{recording.title}</h3>
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>
              {recording.resolution} • {recording.fps}fps • {recording.format} • {recording.size}
            </span>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
            <X size={20} />
          </button>
        </div>

        {/* Video Player Display Container */}
        <div
          style={{
            width: '100%',
            aspectRatio: '16 / 9',
            backgroundColor: '#000',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          <div style={{ textAlign: 'center', color: '#94a3b8' }}>
            <Film size={48} color="#3b82f6" style={{ margin: '0 auto 12px auto' }} />
            <div style={{ fontSize: '14px', color: '#f8fafc', fontWeight: 600 }}>Sẵn sàng phát bản ghi</div>
            <div style={{ fontSize: '12px', marginTop: '4px' }}>Thời lượng: {recording.duration}</div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              backgroundColor: '#3b82f6',
              border: 'none',
              color: '#ffffff',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
};
