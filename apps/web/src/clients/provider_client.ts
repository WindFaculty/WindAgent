/**
 * Decoupled Model Provider Client for WindAgent Web Application (Phase 13).
 */

export interface ProviderMeta {
  name: string;
  status: string;
  models: string[];
}

export class ProviderClient {
  private baseUrl: string;

  constructor(baseUrl: string = "http://localhost:8000") {
    this.baseUrl = baseUrl;
  }

  async listProviders(): Promise<ProviderMeta[]> {
    const res = await fetch(`${this.baseUrl}/api/v2/providers`);
    if (!res.ok) {
      throw new Error(`Provider fetch error: ${res.statusText}`);
    }
    return res.json();
  }
}
