import React, { useRef, useEffect, useState } from 'react';
import { Maximize2, Minimize2 } from 'lucide-react';

export interface TeleprompterPanelProps {
  text: string;
  fontSize: number;
  setFontSize: React.Dispatch<React.SetStateAction<number>>;
  isAutoScroll: boolean;
  setIsAutoScroll: React.Dispatch<React.SetStateAction<boolean>>;
  scrollSpeed: number;
  setScrollSpeed: React.Dispatch<React.SetStateAction<number>>;
}

export const TeleprompterPanel: React.FC<TeleprompterPanelProps> = ({
  text,
  fontSize,
  setFontSize,
  isAutoScroll,
  setIsAutoScroll,
  scrollSpeed,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  // Calculate line & word count
  const lines = text.split('\n').filter((l) => l.trim().length > 0);
  const words = text.split(/\s+/).filter(Boolean).length;

  // Auto-scrolling engine
  useEffect(() => {
    if (!isAutoScroll) return;

    const interval = setInterval(() => {
      if (containerRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
        if (scrollTop + clientHeight >= scrollHeight - 2) {
          // Loop back or stay at bottom
          containerRef.current.scrollTop = 0;
        } else {
          containerRef.current.scrollTop += scrollSpeed;
        }
      }
    }, 40);

    return () => clearInterval(interval);
  }, [isAutoScroll, scrollSpeed]);

  const handleZoomIn = () => {
    setFontSize((prev) => Math.min(28, prev + 2));
  };

  const handleZoomOut = () => {
    setFontSize((prev) => Math.max(12, prev - 2));
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
          Kịch Bản / Teleprompter
        </h3>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button
            onClick={handleZoomOut}
            title="Giảm cỡ chữ"
            style={{
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: 'rgba(15, 23, 42, 0.8)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: '#cbd5e1',
              fontSize: '11px',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            A-
          </button>
          <button
            onClick={handleZoomIn}
            title="Tăng cỡ chữ"
            style={{
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: 'rgba(15, 23, 42, 0.8)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: '#cbd5e1',
              fontSize: '11px',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            A+
          </button>
          <button
            onClick={() => setIsFullscreen((prev) => !prev)}
            title="Toàn màn hình"
            style={{
              padding: '4px',
              borderRadius: '4px',
              backgroundColor: 'rgba(15, 23, 42, 0.8)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: '#cbd5e1',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            {isFullscreen ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
        </div>
      </div>

      {/* Script Prompter Text Window */}
      <div
        ref={containerRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          paddingRight: '6px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          fontSize: `${fontSize}px`,
          lineHeight: '1.7',
          color: '#e2e8f0',
          scrollbarWidth: 'thin',
        }}
      >
        {lines.map((paragraph, idx) => (
          <p
            key={idx}
            style={{
              margin: 0,
              color: idx === 0 ? '#60a5fa' : '#cbd5e1',
              fontWeight: idx === 0 ? 600 : 400,
              transition: 'color 0.2s',
            }}
          >
            {paragraph}
          </p>
        ))}
      </div>

      {/* Footer Info & Auto-scroll Toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingTop: '12px',
          marginTop: '8px',
          borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          fontSize: '12px',
        }}
      >
        <span style={{ color: '#94a3b8' }}>
          Dòng 1/{Math.max(1, lines.length)} • {words} từ
        </span>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ color: '#cbd5e1', fontSize: '11px' }}>Tự động cuộn</span>
          <button
            onClick={() => setIsAutoScroll((prev) => !prev)}
            style={{
              width: '32px',
              height: '18px',
              borderRadius: '9999px',
              backgroundColor: isAutoScroll ? '#3b82f6' : '#334155',
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
                left: isAutoScroll ? '16px' : '2px',
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
  );
};
