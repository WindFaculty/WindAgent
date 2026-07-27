/**
 * Tests for PermissionClient - Permission evaluation client.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

global.fetch = vi.fn();

const mockFetch = global.fetch as vi.Mock;

import { PermissionClient, PermissionEvalResult } from "../permission_client";

describe("PermissionClient", () => {
  let client: PermissionClient;

  beforeEach(() => {
    vi.clearAllMocks();
    client = new PermissionClient("http://localhost:8000");
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe("evaluatePermission", () => {
    it("should evaluate permission successfully", async () => {
      const mockResult: PermissionEvalResult = {
        allowed: true,
        requires_approval: false,
        reason: "Action allowed",
      };
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResult),
      });

      const result = await client.evaluatePermission("execute", "tool:shell");

      expect(result).toEqual(mockResult);
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v2/permissions/evaluate",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "execute", target: "tool:shell" }),
        })
      );
    });

    it("should return requires_approval true when approval needed", async () => {
      const mockResult: PermissionEvalResult = {
        allowed: true,
        requires_approval: true,
        reason: "Requires user approval",
      };
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResult),
      });

      const result = await client.evaluatePermission("delete", "file:/important");
      expect(result.requires_approval).toBe(true);
    });

    it("should return allowed false when denied", async () => {
      const mockResult: PermissionEvalResult = {
        allowed: false,
        requires_approval: false,
        reason: "Action not permitted",
      };
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResult),
      });

      const result = await client.evaluatePermission("admin", "system:shutdown");
      expect(result.allowed).toBe(false);
    });

    it("should throw on HTTP error", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        statusText: "Internal Server Error",
      });

      await expect(client.evaluatePermission("read", "file:/etc/passwd")).rejects.toThrow(
        "Permission evaluate error: Internal Server Error"
      );
    });

    it("should throw on network error", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Network error"));

      await expect(client.evaluatePermission("write", "file:/tmp/test")).rejects.toThrow(
        "Network error"
      );
    });

    it("should handle timeout", async () => {
      mockFetch.mockImplementationOnce(
        () => new Promise((_, reject) => setTimeout(() => reject(new Error("Timeout")), 100))
      );

      await expect(client.evaluatePermission("execute", "tool:slow")).rejects.toThrow("Timeout");
    });

    it("should send correct action and target", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ allowed: true, requires_approval: false, reason: "OK" }),
      });

      await client.evaluatePermission("custom_action", "custom_target");

      const callBody = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(callBody.action).toBe("custom_action");
      expect(callBody.target).toBe("custom_target");
    });
  });
});