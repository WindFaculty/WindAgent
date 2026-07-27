import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiClient, TaskCreatePayload, TaskRecord } from "../api_client";

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("ApiClient", () => {
  let client: ApiClient;
  const baseUrl = "http://localhost:8000";

  beforeEach(() => {
    client = new ApiClient(baseUrl);
    mockFetch.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("constructor", () => {
    it("should use default base URL when none provided", () => {
      const defaultClient = new ApiClient();
      expect(defaultClient).toBeInstanceOf(ApiClient);
    });

    it("should use provided base URL", () => {
      const customClient = new ApiClient("http://custom:9000");
      expect(customClient).toBeInstanceOf(ApiClient);
    });
  });

  describe("createTask", () => {
    const payload: TaskCreatePayload = {
      prompt: "Test task",
      workflow_name: "test_workflow",
      session_id: "session-123",
      parameters: { key: "value" },
    };

    const mockTaskRecord: TaskRecord = {
      task_id: "task-456",
      prompt: "Test task",
      status: "pending",
      workflow_name: "test_workflow",
      session_id: "session-123",
      created_at: new Date().toISOString(),
    };

    it("should create task successfully", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockTaskRecord,
      });

      const result = await client.createTask(payload);

      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/v2/tasks`,
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
      );
      expect(result).toEqual(mockTaskRecord);
    });

    it("should throw on API error", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        statusText: "Internal Server Error",
      });

      await expect(client.createTask(payload)).rejects.toThrow("API error: Internal Server Error");
    });

    it("should handle network errors", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Network error"));

      await expect(client.createTask(payload)).rejects.toThrow("Network error");
    });

    it("should handle RFC 7807 error responses", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
        json: async () => ({
          type: "https://api.windagent.dev/errors/validation",
          title: "Validation Error",
          status: 422,
          detail: "Invalid workflow name",
          instance: "/api/v2/tasks",
        }),
      });

      await expect(client.createTask(payload)).rejects.toThrow("API error: Unprocessable Entity");
    });
  });

  describe("listTasks", () => {
    const mockTasks: TaskRecord[] = [
      {
        task_id: "task-1",
        prompt: "Task 1",
        status: "completed",
        workflow_name: "workflow_a",
        session_id: "session-1",
        created_at: new Date().toISOString(),
      },
      {
        task_id: "task-2",
        prompt: "Task 2",
        status: "running",
        workflow_name: "workflow_b",
        session_id: "session-2",
        created_at: new Date().toISOString(),
      },
    ];

    it("should list tasks successfully", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockTasks,
      });

      const result = await client.listTasks();

      expect(mockFetch).toHaveBeenCalledWith(`${baseUrl}/api/v2/tasks`);
      expect(result).toEqual(mockTasks);
    });

    it("should throw on API error", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        statusText: "Service Unavailable",
      });

      await expect(client.listTasks()).rejects.toThrow("API error: Service Unavailable");
    });

    it("should handle empty response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      const result = await client.listTasks();
      expect(result).toEqual([]);
    });
  });

  describe("getTask", () => {
    const taskId = "task-789";
    const mockTask: TaskRecord = {
      task_id: taskId,
      prompt: "Specific task",
      status: "completed",
      workflow_name: "specific_workflow",
      session_id: "session-456",
      created_at: new Date().toISOString(),
      result: { output: "done" },
    };

    it("should get task by ID successfully", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockTask,
      });

      const result = await client.getTask(taskId);

      expect(mockFetch).toHaveBeenCalledWith(`${baseUrl}/api/v2/tasks/${taskId}`);
      expect(result).toEqual(mockTask);
    });

    it("should throw on 404", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: "Not Found",
      });

      await expect(client.getTask(taskId)).rejects.toThrow("API error: Not Found");
    });

    it("should handle unauthorized", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
      });

      await expect(client.getTask(taskId)).rejects.toThrow("API error: Unauthorized");
    });
  });

  describe("abort/cancellation", () => {
    it("should support AbortController", async () => {
      const controller = new AbortController();
      const payload: TaskCreatePayload = { prompt: "Test" };

      mockFetch.mockImplementationOnce(() =>
        new Promise((_, reject) => {
          controller.signal.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        })
      );

      const promise = client.createTask(payload);
      controller.abort();

      await expect(promise).rejects.toThrow("Aborted");
    });
  });

  describe("timeout handling", () => {
    it("should handle timeout", async () => {
      mockFetch.mockImplementationOnce(
        () => new Promise((_, reject) => setTimeout(() => reject(new Error("Timeout")), 100))
      );

      await expect(client.createTask({ prompt: "Test" })).rejects.toThrow("Timeout");
    });
  });
});