import React, { useState, useMemo } from 'react';
import { Search, Edit3, Zap, MoreVertical, Check, AlertTriangle, XCircle, ChevronRight } from 'lucide-react';
import { ProviderIcon } from './ProviderIcons';

export interface ModelRuleMapping {
  model: string;
  rule: string;
}

export interface ProviderItem {
  id: string;
  name: string;
  subName: string;
  endpoint: string;
  credentialsStatus: 'valid' | 'warning' | 'offline';
  modelsCount: number;
  ruleSet: string;
  status: 'connected' | 'warning' | 'offline';
  apiKeyMasked: string;
  orgId?: string;
  timeoutSec: number;
  maxRetries: number;
  models: string[];
  perModelRules?: ModelRuleMapping[];
  fallbackProvider: string;
  maxTokens: number;
  streaming: boolean;
  enableCache: boolean;
  lastTestLatency?: number;
  lastTestTime?: string;
}

interface ProviderRegistryTableProps {
  providers: ProviderItem[];
  selectedProviderId: string;
  onSelectProvider: (provider: ProviderItem) => void;
  onTestProvider: (provider: ProviderItem) => void;
  onEditProvider: (provider: ProviderItem) => void;
}

export const ProviderRegistryTable: React.FC<ProviderRegistryTableProps> = ({
  providers,
  selectedProviderId,
  onSelectProvider,
  onTestProvider,
  onEditProvider,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'connected' | 'warning' | 'offline'>('all');

  const filteredProviders = useMemo(() => {
    return providers.filter((p) => {
      const matchesSearch =
        p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.endpoint.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.ruleSet.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesStatus =
        statusFilter === 'all' ? true : p.status.toLowerCase() === statusFilter.toLowerCase();

      return matchesSearch && matchesStatus;
    });
  }, [providers, searchQuery, statusFilter]);

  const renderCredentialsBadge = (status: ProviderItem['credentialsStatus']) => {
    if (status === 'valid') {
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            padding: '2px 8px',
            borderRadius: '12px',
            backgroundColor: 'rgba(16, 185, 129, 0.12)',
            color: '#34d399',
            fontSize: '0.72rem',
            fontWeight: 600,
            whiteSpace: 'nowrap',
          }}
        >
          <Check size={11} strokeWidth={3} /> Valid
        </span>
      );
    }
    if (status === 'warning') {
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            padding: '2px 8px',
            borderRadius: '12px',
            backgroundColor: 'rgba(245, 158, 11, 0.14)',
            color: '#fbbf24',
            fontSize: '0.72rem',
            fontWeight: 600,
            whiteSpace: 'nowrap',
          }}
        >
          <AlertTriangle size={11} strokeWidth={2.5} /> Warning
        </span>
      );
    }
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '2px 8px',
          borderRadius: '12px',
          backgroundColor: 'rgba(239, 68, 68, 0.14)',
          color: '#f87171',
          fontSize: '0.72rem',
          fontWeight: 600,
          whiteSpace: 'nowrap',
        }}
      >
        <XCircle size={11} strokeWidth={2.5} /> Offline
      </span>
    );
  };

  const renderStatusBadge = (status: ProviderItem['status']) => {
    if (status === 'connected') {
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            padding: '3px 9px',
            borderRadius: '6px',
            backgroundColor: 'rgba(16, 185, 129, 0.12)',
            color: '#34d399',
            fontSize: '0.72rem',
            fontWeight: 600,
            border: '1px solid rgba(16, 185, 129, 0.25)',
          }}
        >
          Connected
        </span>
      );
    }
    if (status === 'warning') {
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '2px',
            padding: '3px 8px',
            borderRadius: '6px',
            backgroundColor: 'rgba(245, 158, 11, 0.12)',
            color: '#fbbf24',
            fontSize: '0.72rem',
            fontWeight: 600,
            border: '1px solid rgba(245, 158, 11, 0.25)',
          }}
        >
          Warning <ChevronRight size={12} />
        </span>
      );
    }
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '2px',
          padding: '3px 8px',
          borderRadius: '6px',
          backgroundColor: 'rgba(239, 68, 68, 0.12)',
          color: '#f87171',
          fontSize: '0.72rem',
          fontWeight: 600,
          border: '1px solid rgba(239, 68, 68, 0.25)',
        }}
      >
        Offline <ChevronRight size={12} />
      </span>
    );
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'rgba(11, 19, 38, 0.85)',
        borderRadius: '14px',
        border: '1px solid rgba(66, 71, 84, 0.4)',
        backdropFilter: 'blur(16px)',
        overflow: 'hidden',
        height: '100%',
      }}
    >
      {/* Table Header Controls */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px 18px',
          borderBottom: '1px solid rgba(66, 71, 84, 0.3)',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: '1rem',
            fontWeight: 700,
            color: 'var(--text-main, #f8fafc)',
            letterSpacing: '-0.01em',
          }}
        >
          Provider Registry
        </h2>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Search Input */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: 'rgba(17, 24, 39, 0.8)',
              border: '1px solid rgba(66, 71, 84, 0.5)',
              borderRadius: '8px',
              padding: '6px 10px',
              minWidth: '160px',
            }}
          >
            <Search size={13} color="#94a3b8" />
            <input
              type="text"
              placeholder="Search providers..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#f8fafc',
                fontSize: '0.78rem',
                outline: 'none',
                width: '100%',
              }}
            />
          </div>

          {/* Status Filter Dropdown */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as any)}
            style={{
              backgroundColor: 'rgba(17, 24, 39, 0.8)',
              border: '1px solid rgba(66, 71, 84, 0.5)',
              borderRadius: '8px',
              color: '#94a3b8',
              fontSize: '0.78rem',
              padding: '6px 10px',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Status</option>
            <option value="connected">Connected</option>
            <option value="warning">Warning</option>
            <option value="offline">Offline</option>
          </select>
        </div>
      </div>

      {/* Table Content Container */}
      <div style={{ overflowX: 'auto', flex: 1 }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            textAlign: 'left',
            fontSize: '0.78rem',
          }}
        >
          <thead>
            <tr
              style={{
                borderBottom: '1px solid rgba(66, 71, 84, 0.25)',
                color: '#64748b',
                fontWeight: 600,
                fontSize: '0.72rem',
                letterSpacing: '0.02em',
              }}
            >
              <th style={{ padding: '10px 14px' }}>Provider</th>
              <th style={{ padding: '10px 10px' }}>Base URL / Endpoint</th>
              <th style={{ padding: '10px 10px' }}>Credentials</th>
              <th style={{ padding: '10px 10px', textAlign: 'center' }}>Models</th>
              <th style={{ padding: '10px 10px' }}>Rule Set</th>
              <th style={{ padding: '10px 10px' }}>Status</th>
              <th style={{ padding: '10px 14px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredProviders.map((provider) => {
              const isSelected = provider.id === selectedProviderId;

              return (
                <tr
                  key={provider.id}
                  onClick={() => onSelectProvider(provider)}
                  style={{
                    borderBottom: '1px solid rgba(66, 71, 84, 0.2)',
                    backgroundColor: isSelected
                      ? 'rgba(59, 130, 246, 0.12)'
                      : 'transparent',
                    cursor: 'pointer',
                    transition: 'background-color 0.12s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.03)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }
                  }}
                >
                  {/* Provider Brand & Name */}
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <ProviderIcon providerId={provider.id} size={28} />
                      <div>
                        <div
                          style={{
                            fontWeight: 700,
                            color: isSelected ? '#60a5fa' : 'var(--text-main, #f8fafc)',
                            fontSize: '0.82rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                          }}
                        >
                          {provider.name}
                        </div>
                        <div style={{ fontSize: '0.68rem', color: '#64748b' }}>
                          {provider.subName}
                        </div>
                      </div>
                    </div>
                  </td>

                  {/* Base URL / Endpoint */}
                  <td style={{ padding: '10px 10px' }}>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: '0.72rem',
                        color: '#94a3b8',
                        maxWidth: '180px',
                        display: 'inline-block',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={provider.endpoint}
                    >
                      {provider.endpoint}
                    </span>
                  </td>

                  {/* Credentials */}
                  <td style={{ padding: '10px 10px' }}>
                    {renderCredentialsBadge(provider.credentialsStatus)}
                  </td>

                  {/* Models Count */}
                  <td style={{ padding: '10px 10px', textAlign: 'center', fontWeight: 600, color: '#e2e8f0' }}>
                    {provider.modelsCount}
                  </td>

                  {/* Rule Set */}
                  <td style={{ padding: '10px 10px' }}>
                    <span
                      style={{
                        fontSize: '0.72rem',
                        color: '#cbd5e1',
                        backgroundColor: 'rgba(255, 255, 255, 0.05)',
                        padding: '2px 7px',
                        borderRadius: '4px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {provider.ruleSet}
                    </span>
                  </td>

                  {/* Status Badge */}
                  <td style={{ padding: '10px 10px' }}>
                    {renderStatusBadge(provider.status)}
                  </td>

                  {/* Actions */}
                  <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                    <div
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        onClick={() => onEditProvider(provider)}
                        title="Edit Provider"
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: '#94a3b8',
                          cursor: 'pointer',
                          padding: '4px',
                          borderRadius: '4px',
                          display: 'flex',
                          alignItems: 'center',
                        }}
                      >
                        <Edit3 size={13} />
                      </button>
                      <button
                        type="button"
                        onClick={() => onTestProvider(provider)}
                        title="Test Connection"
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: '#60a5fa',
                          cursor: 'pointer',
                          padding: '4px',
                          borderRadius: '4px',
                          display: 'flex',
                          alignItems: 'center',
                        }}
                      >
                        <Zap size={13} />
                      </button>
                      <button
                        type="button"
                        title="More Options"
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: '#64748b',
                          cursor: 'pointer',
                          padding: '4px',
                          borderRadius: '4px',
                          display: 'flex',
                          alignItems: 'center',
                        }}
                      >
                        <MoreVertical size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}

            {filteredProviders.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: '32px', textAlign: 'center', color: '#64748b' }}>
                  No providers found matching your filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Table Footer */}
      <div
        style={{
          padding: '12px 18px',
          borderTop: '1px solid rgba(66, 71, 84, 0.25)',
          fontSize: '0.72rem',
          color: '#64748b',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span>
          Showing 1 to {filteredProviders.length} of {providers.length} providers
        </span>
      </div>
    </div>
  );
};
