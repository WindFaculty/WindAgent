/**
 * Canonical Studio V3 Capabilities and Runtime Contracts.
 */

export interface CapabilitySummary {
  name: string;
  status: 'AVAILABLE' | 'DEGRADED' | 'UNAVAILABLE' | string;
  detail?: string | null;
}

export interface RuntimeCapabilityProfile {
  capabilities: CapabilitySummary[];
  fail_closed_flags: string[];
  certification_mode: boolean;
}

export interface ReadinessResponse {
  status: 'READY' | 'DEGRADED' | 'UNAVAILABLE' | string;
  capabilities: Record<string, string>;
  fail_closed_flags: string[];
  certification_mode: boolean;
}
