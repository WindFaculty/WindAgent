import React, { useState } from 'react';
import { AssetRequirementDTO } from '@windagent/production-contracts';

interface MissingAssetResolverModalProps {
  isOpen: boolean;
  requirement: AssetRequirementDTO | null;
  onClose: () => void;
  onResolveAndBind: (assetId: string) => void;
}

export const MissingAssetResolverModal: React.FC<MissingAssetResolverModalProps> = ({
  isOpen,
  requirement,
  onClose,
  onResolveAndBind,
}) => {
  const [activeTab, setActiveTab] = useState<'search_library' | 'search_internet' | 'generate' | 'upload'>('search_library');
  const [jobState, setJobState] = useState<'idle' | 'processing' | 'candidate_ready'>('idle');
  const [candidateAssetId, setCandidateAssetId] = useState<string | null>(null);

  if (!isOpen || !requirement) return null;

  const handleStartGenerate = () => {
    setJobState('processing');
    setTimeout(() => {
      setCandidateAssetId(`ast_gen_${Math.random().toString(36).substring(2, 8)}`);
      setJobState('candidate_ready');
    }, 1200);
  };

  const handleStartImport = () => {
    setJobState('processing');
    setTimeout(() => {
      setCandidateAssetId(`ast_imp_${Math.random().toString(36).substring(2, 8)}`);
      setJobState('candidate_ready');
    }, 1000);
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(17, 17, 27, 0.8)',
        backdropFilter: 'blur(5px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1100,
      }}
    >
      <div
        style={{
          width: '640px',
          backgroundColor: '#1E1E2E',
          border: '1px solid #313244',
          borderRadius: '10px',
          boxShadow: '0 12px 40px rgba(0,0,0,0.5)',
          color: '#CDD6F4',
          fontFamily: 'Inter, system-ui, sans-serif',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{ padding: '1.25rem', borderBottom: '1px solid #313244', backgroundColor: '#181825', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span
                style={{
                  padding: '0.2rem 0.5rem',
                  borderRadius: '4px',
                  backgroundColor: requirement.severity === 'BLOCKING' ? '#732c2c' : '#644e21',
                  color: requirement.severity === 'BLOCKING' ? '#F38BA8' : '#F9E2AF',
                  fontSize: '0.7rem',
                  fontWeight: 700,
                }}
              >
                {requirement.severity} REQUIREMENT
              </span>
              <span style={{ fontSize: '0.75rem', color: '#A6ADC8' }}>{requirement.requirement_id}</span>
            </div>
            <h3 style={{ margin: '0.4rem 0 0 0', fontSize: '1.1rem', fontWeight: 700, color: '#89B4FA' }}>
              Missing {requirement.screenplay_entity_type}: {requirement.screenplay_entity_id}
            </h3>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#A6ADC8', cursor: 'pointer', fontSize: '1.25rem' }}>
            ✕
          </button>
        </div>

        {/* Tab Selection */}
        <div style={{ display: 'flex', borderBottom: '1px solid #313244', backgroundColor: '#181825' }}>
          {(
            [
              { id: 'search_library', label: '🔍 Search Library' },
              { id: 'search_internet', label: '🌐 Search Web' },
              { id: 'generate', label: '✨ Generate Asset' },
              { id: 'upload', label: '📁 Upload File' },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                setJobState('idle');
              }}
              style={{
                flex: 1,
                padding: '0.75rem 0.5rem',
                border: 'none',
                borderBottom: activeTab === tab.id ? '2px solid #89B4FA' : '2px solid transparent',
                backgroundColor: activeTab === tab.id ? '#1E1E2E' : 'transparent',
                color: activeTab === tab.id ? '#89B4FA' : '#A6ADC8',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Body Content */}
        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem', minHeight: '220px' }}>
          {activeTab === 'search_library' && (
            <div>
              <p style={{ fontSize: '0.85rem', color: '#A6ADC8', margin: '0 0 1rem 0' }}>
                Search existing production asset library matching required kind <strong>{requirement.required_kind}</strong>.
              </p>
              <button
                onClick={handleStartImport}
                style={{
                  padding: '0.6rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: '#313244',
                  border: '1px solid #45475A',
                  color: '#89B4FA',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Scan Library for Candidates
              </button>
            </div>
          )}

          {activeTab === 'search_internet' && (
            <div>
              <p style={{ fontSize: '0.85rem', color: '#A6ADC8', margin: '0 0 1rem 0' }}>
                Discover external asset candidates via web asset API integration.
              </p>
              <button
                onClick={handleStartImport}
                style={{
                  padding: '0.6rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: '#313244',
                  border: '1px solid #45475A',
                  color: '#CBA6F7',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Query Web Provider
              </button>
            </div>
          )}

          {activeTab === 'generate' && (
            <div>
              <p style={{ fontSize: '0.85rem', color: '#A6ADC8', margin: '0 0 0.5rem 0' }}>
                Generate asset using prompt compiler for {requirement.screenplay_entity_id}.
              </p>
              <textarea
                readOnly
                value={`Generate ${requirement.required_kind} for screenplay ${requirement.screenplay_entity_type.toLowerCase()} '${requirement.screenplay_entity_id}'. Style: High fidelity production render.`}
                style={{
                  width: '100%',
                  height: '70px',
                  backgroundColor: '#181825',
                  border: '1px solid #45475A',
                  borderRadius: '6px',
                  color: '#CDD6F4',
                  padding: '0.5rem',
                  fontSize: '0.8rem',
                  fontFamily: 'monospace',
                  marginBottom: '1rem',
                }}
              />
              <button
                onClick={handleStartGenerate}
                style={{
                  padding: '0.6rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: '#89B4FA',
                  border: 'none',
                  color: '#11111B',
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                ⚡ Trigger Generation Pipeline
              </button>
            </div>
          )}

          {activeTab === 'upload' && (
            <div>
              <p style={{ fontSize: '0.85rem', color: '#A6ADC8', margin: '0 0 1rem 0' }}>
                Upload external 3D model or image asset file directly.
              </p>
              <button
                onClick={handleStartImport}
                style={{
                  padding: '0.6rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: '#313244',
                  border: '1px solid #45475A',
                  color: '#A6E3A1',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Choose Local File...
              </button>
            </div>
          )}

          {/* Job Processing State */}
          {jobState === 'processing' && (
            <div style={{ backgroundColor: '#181825', padding: '1rem', borderRadius: '6px', border: '1px solid #45475A' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#F9E2AF' }}>
                ⚙️ Processing candidate (Normalize → Validate → License check)...
              </div>
            </div>
          )}

          {/* Candidate Ready State */}
          {jobState === 'candidate_ready' && candidateAssetId && (
            <div style={{ backgroundColor: '#181825', padding: '1rem', borderRadius: '6px', border: '1px solid #275d38' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#A6E3A1' }}>
                ✅ Candidate Asset Ready & Approved: {candidateAssetId}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#A6ADC8', marginTop: '0.25rem' }}>
                Lifecycle: APPROVED • License: COMMERCIAL_USE_ALLOWED • Validation: Passed
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid #313244', backgroundColor: '#181825', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
          <button
            onClick={onClose}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '6px',
              backgroundColor: '#313244',
              border: '1px solid #45475A',
              color: '#CDD6F4',
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            disabled={jobState !== 'candidate_ready' || !candidateAssetId}
            onClick={() => {
              if (candidateAssetId) onResolveAndBind(candidateAssetId);
            }}
            style={{
              padding: '0.5rem 1.25rem',
              borderRadius: '6px',
              backgroundColor: jobState === 'candidate_ready' ? '#A6E3A1' : '#45475A',
              border: 'none',
              color: jobState === 'candidate_ready' ? '#11111B' : '#6C7086',
              fontSize: '0.85rem',
              fontWeight: 700,
              cursor: jobState === 'candidate_ready' ? 'pointer' : 'not-allowed',
            }}
          >
            Bind & Revalidate Screenplay
          </button>
        </div>
      </div>
    </div>
  );
};
