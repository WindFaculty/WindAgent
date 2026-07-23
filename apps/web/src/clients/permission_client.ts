/**
 * Decoupled Permission Client for WindAgent Web Application (Phase 13).
 */

export interface PermissionEvalResult {
  allowed: boolean;
  requires_approval: boolean;
  reason: string;
}

export class PermissionClient {
  private baseUrl: string;

  constructor(baseUrl: string = "http://localhost:8000") {
    this.baseUrl = baseUrl;
  }

  async evaluatePermission(action: string, target: string): Promise<PermissionEvalResult> {
    const res = await fetch(`${this.baseUrl}/api/v2/permissions/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, target }),
    });
    if (!res.ok) {
      throw new Error(`Permission evaluate error: ${res.statusText}`);
    }
    return res.json();
  }
}
