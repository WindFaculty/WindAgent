/**
 * Decoupled API Client for WindAgent Web Application (Phase 13).
 * Interacts with WindAgent V2 API endpoints (/api/v2/tasks, /api/v2/runs).
 */

export interface TaskCreatePayload {
  prompt: string;
  workflow_name?: string;
  session_id?: string;
  parameters?: Record<string, any>;
}

export interface TaskRecord {
  task_id: string;
  prompt: string;
  status: string;
  workflow_name: string;
  session_id: string;
  created_at: string;
  result?: Record<string, any>;
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = "http://localhost:8000") {
    this.baseUrl = baseUrl;
  }

  async createTask(payload: TaskCreatePayload): Promise<TaskRecord> {
    const res = await fetch(`${this.baseUrl}/api/v2/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`API error: ${res.statusText}`);
    }
    return res.json();
  }

  async listTasks(): Promise<TaskRecord[]> {
    const res = await fetch(`${this.baseUrl}/api/v2/tasks`);
    if (!res.ok) {
      throw new Error(`API error: ${res.statusText}`);
    }
    return res.json();
  }

  async getTask(taskId: string): Promise<TaskRecord> {
    const res = await fetch(`${this.baseUrl}/api/v2/tasks/${taskId}`);
    if (!res.ok) {
      throw new Error(`API error: ${res.statusText}`);
    }
    return res.json();
  }

  async cancelTask(taskId: string): Promise<TaskRecord> {
    const res = await fetch(`${this.baseUrl}/api/v2/tasks/${taskId}/cancel`, {
      method: "POST",
    });
    if (!res.ok) {
      throw new Error(`API error: ${res.statusText}`);
    }
    return res.json();
  }
}
