import React from 'react';
import { ScreenplayChangeImpactDTO } from '@windagent/production-contracts';

interface ProductionImpactViewProps {
  impact: ScreenplayChangeImpactDTO | null;
}

export const ProductionImpactView: React.FC<ProductionImpactViewProps> = ({ impact }) => {
  if (!impact) {
    return <div style={{ padding: '1rem', color: '#6C7086', fontSize: '0.85rem' }}>No impact analysis performed yet.</div>;
  }

  return (
    <div style={{ padding: '1rem', fontFamily: 'Inter, system-ui, sans-serif', color: '#CDD6F4' }}>
      {impact.is_high_impact && (
        <div
          style={{
            backgroundColor: '#452A3A',
            border: '1px solid #F38BA8',
            color: '#F38BA8',
            padding: '0.75rem',
            borderRadius: '6px',
            fontSize: '0.8rem',
            fontWeight: 700,
            marginBottom: '1rem',
          }}
        >
          ⚠️ HIGH IMPACT: {impact.warning_message}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem' }}>
        <div style={{ backgroundColor: '#181825', padding: '0.75rem', borderRadius: '6px', border: '1px solid #313244' }}>
          <div style={{ fontSize: '0.7rem', color: '#A6ADC8' }}>AFFECTED SHOTS</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#89B4FA' }}>{impact.affected_shots.length}</div>
        </div>
        <div style={{ backgroundColor: '#181825', padding: '0.75rem', borderRadius: '6px', border: '1px solid #313244' }}>
          <div style={{ fontSize: '0.7rem', color: '#A6ADC8' }}>AFFECTED AUDIO</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#CBA6F7' }}>{impact.affected_audio.length}</div>
        </div>
        <div style={{ backgroundColor: '#181825', padding: '0.75rem', borderRadius: '6px', border: '1px solid #313244' }}>
          <div style={{ fontSize: '0.7rem', color: '#A6ADC8' }}>AFFECTED RENDERS</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#FAB387' }}>{impact.affected_renders.length}</div>
        </div>
        <div style={{ backgroundColor: '#181825', padding: '0.75rem', borderRadius: '6px', border: '1px solid #313244' }}>
          <div style={{ fontSize: '0.7rem', color: '#A6ADC8' }}>INTENT POLICY</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#A6E3A1' }}>{impact.invalidation_intent}</div>
        </div>
      </div>
    </div>
  );
};
