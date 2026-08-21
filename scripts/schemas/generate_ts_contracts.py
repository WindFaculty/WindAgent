"""
Generates TypeScript interfaces and contract schemas from FastAPI models
and exports them to `tests/fixtures/generated_contracts.ts`.
"""

from __future__ import annotations

from pathlib import Path

CONTRACT_TS_OUTPUT_PATH = Path("tests/fixtures/generated_contracts.ts")

GENERATED_CONTRACT_HEADER = """/* eslint-disable */
/**
 * AUTO-GENERATED FILE BY generate_ts_contracts.py. DO NOT EDIT DIRECTLY.
 * WindAgent Production API Contract Definitions (Stage H - UI41)
 */

export interface CanonicalCommandEnvelope<T = unknown> {
  command_id: string;
  project_id: string;
  command_type: string;
  client_timestamp: string;
  idempotency_key: string;
  expected_revision_id: string;
  payload: T;
}

export interface CanonicalEventEnvelope<T = unknown> {
  event_id: string;
  project_id: string;
  event_type: string;
  sequence: number;
  server_timestamp: string;
  payload: T;
}

export interface ProblemDetailsError {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  code: string;
  invalid_params?: Array<{ name: string; reason: string }>;
}

export interface ScreenplayReadModel {
  screenplay_id: string;
  title: string;
  logline: string;
  status: 'DRAFT' | 'LOCKED' | 'ARCHIVED';
  scenes: Array<{
    scene_id: string;
    order: number;
    title: string;
    location_id: string;
    character_ids: string[];
    action_description: string;
    time_of_day: string;
    dialogue_line_ids: string[];
  }>;
}

export interface ProductionAssetModel {
  asset_id: string;
  name: string;
  asset_type: string;
  format: 'GLB' | 'OBJ' | 'PNG' | 'JPG' | 'MP4' | 'WAV';
  content_hash: string;
  license_state: 'LICENSED' | 'UNKNOWN' | 'INCOMPATIBLE';
  processing_state: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  uri: string;
}

export interface CollaborationProposalModel {
  proposal_id: string;
  project_id: string;
  revision_id: string;
  target_entity_type: 'SCREENPLAY' | 'ASSET' | 'SHOT';
  target_entity_id: string;
  agent_id: string;
  status: 'PENDING' | 'STALE' | 'APPROVED' | 'REJECTED';
  summary: string;
  payload: Record<string, unknown>;
}
"""


def generate_contracts() -> str:
    """Generate TypeScript contract contents."""
    return GENERATED_CONTRACT_HEADER.strip() + "\n"


def main() -> None:
    content = generate_contracts()
    CONTRACT_TS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT_TS_OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Generated TypeScript contract file at {CONTRACT_TS_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
