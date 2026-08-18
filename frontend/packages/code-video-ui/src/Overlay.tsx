import React from 'react';
import { Annotation } from './types';

export interface OverlayProps {
  annotations?: Annotation[];
}

export const Overlay: React.FC<OverlayProps> = ({ annotations = [] }) => {
  if (!annotations.length) return null;

  return (
    <div className="overlay-layer" style={{ pointerEvents: 'none', position: 'absolute', inset: 0 }}>
      {annotations.map((ann) => (
        <div
          key={ann.annotation_id}
          className={`annotation-badge badge-${ann.kind}`}
          style={{
            position: 'absolute',
            bottom: 24,
            right: 24,
            background: 'rgba(88, 166, 255, 0.9)',
            color: '#fff',
            padding: '8px 16px',
            borderRadius: 8,
            boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
            fontWeight: 600,
            fontSize: 14,
          }}
        >
          {ann.text || ann.target_symbol || ann.kind}
        </div>
      ))}
    </div>
  );
};
