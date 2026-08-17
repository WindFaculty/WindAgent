/**
 * Legacy V2 Asset Contracts.
 * @deprecated Use AssetResource from projects.ts (Phase 9 canonical V3 asset).
 */

import type { ResourceBase } from './resource';

/** @deprecated Migrate to the canonical AssetResource from Phase 9 (projects.ts). */
export interface LegacyAssetResource extends ResourceBase {
  name: string;
  asset_type: 'IMAGE' | 'AUDIO' | '3D_MODEL' | 'VIDEO' | 'PRESET' | string;
  storage_uri: string;
  mime_type: string;
  size_bytes: number;
  checksum_sha256: string;
  metadata?: Record<string, unknown>;
}
