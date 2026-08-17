import React from 'react';

interface AgentTerminalProps {
  events: Record<string, unknown>[];
}

export const AgentTerminal: React.FC<AgentTerminalProps> = ({ events }) => {
  return (
    <div
      style={{
        background: '#030712',
        border: '1px solid #1f2937',
        borderRadius: '12px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        fontFamily: 'var(--font-mono, monospace)',
        height: '240px',
        overflowY: 'auto',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #1f2937', paddingBottom: '8px' }}>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#9ca3af' }}>Workspace Event Stream & Output</span>
        <span style={{ fontSize: '0.7rem', color: '#10b981' }}>● LIVE (DURABLE PROJECTION)</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.75rem' }}>
        {events.length === 0 ? (
          <span style={{ color: '#4b5563' }}>No events recorded for this conversation yet.</span>
        ) : (
          events.map((evt, idx) => {
            const time = evt.timestamp ? new Date(String(evt.timestamp)).toLocaleTimeString() : '00:00:00';
            const eventType = String(evt.event_type || evt.type || 'system.event');
            return (
              <div key={idx} style={{ display: 'flex', gap: '8px', color: '#d1d5db', lineHeight: 1.4 }}>
                <span style={{ color: '#6b7280' }}>[{time}]</span>
                <span style={{ color: '#38bdf8', fontWeight: 600 }}>{eventType}</span>
                <span style={{ color: '#9ca3af' }}>{JSON.stringify(evt.payload || evt)}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
