import React, { useState } from 'react';

interface AssetPickerModalProps {
  isOpen: boolean;
  entityType: 'CHARACTER' | 'LOCATION' | 'PROP';
  entityId: string;
  entityName: string;
  onClose: () => void;
  onConfirmBind: (assetId: string, roleKey: string) => void;
}

interface MockCandidateAsset {
  id: string;
  name: string;
  kind: string;
  lifecycleState: 'APPROVED' | 'BOUND_TO_PROJECT' | 'DOWNLOADED' | 'REJECTED';
  licenseState: 'COMMERCIAL_USE_ALLOWED' | 'UNKNOWN' | 'CREATIVE_COMMONS';
}

const MOCK_CANDIDATE_ASSETS: MockCandidateAsset[] = [
  {
    id: 'asset_bunny',
    name: 'Bunny Hero Model v2',
    kind: 'CHARACTER_3D_MODEL',
    lifecycleState: 'APPROVED',
    licenseState: 'COMMERCIAL_USE_ALLOWED',
  },
  {
    id: 'asset_park',
    name: 'Sunny City Park Environment',
    kind: 'LOCATION_3D_ENVIRONMENT',
    lifecycleState: 'APPROVED',
    licenseState: 'COMMERCIAL_USE_ALLOWED',
  },
  {
    id: 'asset_ball_01',
    name: 'Red Beach Ball 3D Asset',
    kind: 'PROP_3D_OBJECT',
    lifecycleState: 'APPROVED',
    licenseState: 'COMMERCIAL_USE_ALLOWED',
  },
  {
    id: 'asset_ball_draft',
    name: 'Raw Ball Scan (Unapproved)',
    kind: 'PROP_3D_OBJECT',
    lifecycleState: 'DOWNLOADED',
    licenseState: 'UNKNOWN',
  },
];

export const AssetPickerModal: React.FC<AssetPickerModalProps> = ({
  isOpen,
  entityType,
  entityId,
  entityName,
  onClose,
  onConfirmBind,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

  if (!isOpen) return null;

  const filteredAssets = MOCK_CANDIDATE_ASSETS.filter((a) =>
    a.name.toLowerCase().includes(searchTerm.toLowerCase()) || a.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const selectedAsset = MOCK_CANDIDATE_ASSETS.find((a) => a.id === selectedAssetId);
  const isEligible = selectedAsset ? selectedAsset.lifecycleState === 'APPROVED' && selectedAsset.licenseState !== 'UNKNOWN' : false;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(17, 17, 27, 0.75)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        style={{
          width: '560px',
          backgroundColor: '#1E1E2E',
          border: '1px solid #313244',
          borderRadius: '8px',
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          color: '#CDD6F4',
          fontFamily: 'Inter, system-ui, sans-serif',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{ padding: '1.25rem', borderBottom: '1px solid #313244', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#89B4FA' }}>
              Select Asset to Bind
            </h3>
            <div style={{ fontSize: '0.75rem', color: '#A6ADC8', marginTop: '0.25rem' }}>
              Binding to {entityType} <strong style={{ color: '#F9E2AF' }}>{entityName}</strong> ({entityId})
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#A6ADC8', cursor: 'pointer', fontSize: '1.25rem' }}>
            ✕
          </button>
        </div>

        {/* Search */}
        <div style={{ padding: '1rem 1.25rem 0.5rem 1.25rem' }}>
          <input
            type="text"
            placeholder="Search candidate assets by name or ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              padding: '0.6rem 0.8rem',
              backgroundColor: '#181825',
              border: '1px solid #45475A',
              borderRadius: '6px',
              color: '#CDD6F4',
              fontSize: '0.85rem',
              outline: 'none',
            }}
          />
        </div>

        {/* Asset List */}
        <div style={{ padding: '0.5rem 1.25rem', maxHeight: '280px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {filteredAssets.map((asset) => {
            const selected = asset.id === selectedAssetId;
            const eligible = asset.lifecycleState === 'APPROVED' && asset.licenseState !== 'UNKNOWN';
            return (
              <div
                key={asset.id}
                onClick={() => setSelectedAssetId(asset.id)}
                style={{
                  padding: '0.75rem',
                  borderRadius: '6px',
                  backgroundColor: selected ? '#313244' : '#181825',
                  border: selected ? '1px solid #89B4FA' : '1px solid #313244',
                  cursor: 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#CDD6F4' }}>{asset.name}</div>
                  <div style={{ fontSize: '0.75rem', color: '#A6ADC8', marginTop: '0.2rem' }}>
                    ID: {asset.id} • Kind: {asset.kind}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.35rem' }}>
                  <span
                    style={{
                      padding: '0.2rem 0.45rem',
                      borderRadius: '4px',
                      fontSize: '0.65rem',
                      fontWeight: 700,
                      backgroundColor: eligible ? '#275d38' : '#732c2c',
                      color: eligible ? '#A6E3A1' : '#F38BA8',
                    }}
                  >
                    {eligible ? 'ELIGIBLE' : 'INELIGIBLE'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid #313244', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', backgroundColor: '#181825' }}>
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
            disabled={!selectedAssetId || !isEligible}
            onClick={() => {
              if (selectedAssetId) onConfirmBind(selectedAssetId, 'primary');
            }}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '6px',
              backgroundColor: selectedAssetId && isEligible ? '#89B4FA' : '#45475A',
              border: 'none',
              color: selectedAssetId && isEligible ? '#11111B' : '#6C7086',
              fontSize: '0.85rem',
              fontWeight: 700,
              cursor: selectedAssetId && isEligible ? 'pointer' : 'not-allowed',
            }}
          >
            Confirm Binding
          </button>
        </div>
      </div>
    </div>
  );
};
