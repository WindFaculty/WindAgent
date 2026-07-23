/**
 * Decoupled Artifact Client for WindAgent Web Application (Phase 13).
 */

export interface ArtifactMeta {
  artifact_id: string;
  name: string;
  mime_type: string;
  size_bytes: number;
}

export class ArtifactClient {
  private baseUrl: string;

  constructor(baseUrl: string = "http://localhost:8000") {
    this.baseUrl = baseUrl;
  }

  async listArtifacts(): Promise<ArtifactMeta[]> {
    const res = await fetch(`${this.baseUrl}/api/v2/artifacts`);
    if (!res.ok) {
      throw new Error(`Artifact fetch error: ${res.statusText}`);
    }
    return res.json();
  }
}
