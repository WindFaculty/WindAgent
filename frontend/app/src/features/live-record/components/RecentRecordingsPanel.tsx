import React, { useState } from 'react';
import { MoreVertical, Play, FolderOpen, Film } from 'lucide-react';
import type { RecentRecording } from '../hooks/useLiveRecord';

export interface RecentRecordingsPanelProps {
  recordings: RecentRecording[];
  onSelectPlayback: (rec: RecentRecording) => void;
  onViewAll?: () => void;
}

export const RecentRecordingsPanel: React.FC<RecentRecordingsPanelProps> = ({
  recordings,
  onSelectPlayback,
  onViewAll,
}) => {
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);

  const toggleMenu = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setActiveMenuId((prev) => (prev === id ? null : id));
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
        height: '100%',
        boxShadow: '0 8px 24px -6px rgba(0, 0, 0, 0.5)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '12px',
          paddingBottom: '10px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>
          Bản Ghi Gần Đây
        </h3>
        <button
          onClick={onViewAll}
          style={{
            background: 'none',
            border: 'none',
            color: '#60a5fa',
            fontSize: '12px',
            fontWeight: 600,
            cursor: 'pointer',
            padding: 0,
          }}
        >
          Xem tất cả
        </button>
      </div>

      {/* Recording List */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          flex: 1,
          overflowY: 'auto',
          paddingRight: '4px',
        }}
      >
        {recordings.map((rec, index) => (
          <div
            key={rec.id}
            onClick={() => onSelectPlayback(rec)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '8px',
              borderRadius: '10px',
              backgroundColor: 'rgba(15, 23, 42, 0.6)',
              border: '1px solid rgba(255, 255, 255, 0.05)',
              cursor: 'pointer',
              position: 'relative',
              transition: 'background-color 0.15s',
            }}
          >
            {/* Thumbnail */}
            <div
              style={{
                width: '74px',
                height: '46px',
                borderRadius: '6px',
                backgroundColor: '#0f172a',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                position: 'relative',
                overflow: 'hidden',
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'radial-gradient(circle at center, #1e3a8a 0%, #090d16 100%)',
              }}
            >
              {/* Mini presenter avatar thumbnail preview */}
              <div
                style={{
                  width: '24px',
                  height: '24px',
                  borderRadius: '50%',
                  backgroundColor: '#3b82f6',
                  opacity: 0.8,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Film size={12} color="#ffffff" />
              </div>

              {index === 0 && (
                <span
                  style={{
                    position: 'absolute',
                    top: '2px',
                    left: '2px',
                    backgroundColor: '#ef4444',
                    color: '#ffffff',
                    fontSize: '7px',
                    fontWeight: 800,
                    padding: '1px 3px',
                    borderRadius: '2px',
                  }}
                >
                  REC
                </span>
              )}

              <span
                style={{
                  position: 'absolute',
                  bottom: '2px',
                  right: '3px',
                  backgroundColor: 'rgba(0, 0, 0, 0.75)',
                  color: '#ffffff',
                  fontSize: '9px',
                  fontFamily: 'monospace',
                  fontWeight: 600,
                  padding: '1px 3px',
                  borderRadius: '2px',
                }}
              >
                {rec.duration}
              </span>
            </div>

            {/* Info */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <h4
                style={{
                  margin: '0 0 2px 0',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#f8fafc',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {rec.title}
              </h4>
              <div style={{ fontSize: '10px', color: '#60a5fa', marginBottom: '2px' }}>
                • {rec.resolution} • {rec.fps}fps • {rec.format}
              </div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: '10px',
                  color: '#94a3b8',
                }}
              >
                <span>
                  {rec.time} • {rec.date}
                </span>
                <span style={{ fontWeight: 600, color: '#cbd5e1' }}>{rec.size}</span>
              </div>
            </div>

            {/* Menu Button */}
            <div style={{ position: 'relative' }}>
              <button
                onClick={(e) => toggleMenu(e, rec.id)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  padding: '4px',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                <MoreVertical size={14} />
              </button>

              {activeMenuId === rec.id && (
                <div
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: '24px',
                    backgroundColor: '#1e293b',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '8px',
                    padding: '4px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '2px',
                    width: '120px',
                    zIndex: 50,
                    boxShadow: '0 10px 25px rgba(0, 0, 0, 0.6)',
                  }}
                >
                  <button
                    onClick={() => {
                      onSelectPlayback(rec);
                      setActiveMenuId(null);
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '6px 8px',
                      background: 'none',
                      border: 'none',
                      color: '#f8fafc',
                      fontSize: '11px',
                      cursor: 'pointer',
                      borderRadius: '4px',
                      textAlign: 'left',
                    }}
                  >
                    <Play size={12} /> Phát clip
                  </button>
                  <button
                    onClick={() => setActiveMenuId(null)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '6px 8px',
                      background: 'none',
                      border: 'none',
                      color: '#94a3b8',
                      fontSize: '11px',
                      cursor: 'pointer',
                      borderRadius: '4px',
                      textAlign: 'left',
                    }}
                  >
                    <FolderOpen size={12} /> Mở thư mục
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
