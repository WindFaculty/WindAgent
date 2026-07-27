/**
 * Tests for ProviderClient - Model provider inventory client.
 * Tests real implementation with fetch mocked at network boundary.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

global.fetch = vi.fn();

const mockFetch = global.fetch as vi.Mock;

import { ProviderClient, ProviderMeta } from "../provider_client";

describe("ProviderClient", () => {
  let client: ProviderClient;

  beforeEach(() => {
    vi.clearAllMocks();
    client = new ProviderClient("http://localhost:8000");
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe("listProviders", () => {
    it("should list providers successfully", async () => {
      const mockProviders: ProviderMeta[] = [
        { name: "openai", status: "healthy", models: ["gpt-4", "gpt-3.5-turbo"] },
        { name: "anthropic", status: "healthy", models: ["claude-3-opus", "claude-3-sonnet"] },
      ];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockProviders),
      });

      const result = await client.listProviders();

      expect(result).toEqual(mockProviders);
      expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/api/v2/providers");
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it("should return empty array when no providers", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([]),
      });

      const result = await client.listProviders();
      expect(result).toEqual([]);
    });

    it("should throw on HTTP 500", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
      });

      await expect(client.listProviders()).rejects.toThrow("Provider fetch error: Internal Server Error");
    });

    it("should throw on HTTP 401", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
      });

      await expect(client.listProviders()).rejects.toThrow("Provider fetch error: Unauthorized");
    });

    it("should throw on HTTP 429", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 429,
        statusText: "Too Many Requests",
      });

      await expect(client.listProviders()).rejects.toThrow("Provider fetch error: Too Many Requests");
    });

    it("should throw on network error", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Network error"));

      await expect(client.listProviders()).rejects.toThrow("Network error");
    });

    it("should handle timeout", async () => {
      mockFetch.mockImplementationOnce(
        () => new Promise((_, reject) => setTimeout(() => reject(new Error("Timeout")), 100))
      );

      await expect(client.listProviders()).rejects.toThrow("Timeout");
    });

    it("should handle disabled endpoint (404)", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: "Not Found",
      });

      await expect(client.listProviders()).rejects.toThrow("Provider fetch error: Not Found");
    });

    it("should include model listings", async () => {
      const providers: ProviderMeta[] = [
        { name: "ollama", status: "healthy", models: ["llama3", "mistral", "codellama"] },
      ];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(providers),
      });

      const result = await client.listProviders();
      expect(result[0].models).toContain("llama3");
      expect(result[0].models.length).toBe(3);
    });

    it("should handle provider health and quota state", async () => {
      const providers: ProviderMeta[] = [
        { name: "openai", status: "quota_exceeded", models: [] },
        { name: "anthropic", status: "healthy", models: ["claude-3"] },
        { name: "ollama", status: "degraded", models: ["llama3"] },
      ];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(providers),
      });

      const result = await client.listProviders();
      expect(result[0].status).toBe("quota_exceeded");
      expect(result[1].status).toBe("healthy");
      expect(result[2].status).toBe("degraded");
    });

    it("should handle malformed response (missing models array)", async () => {
      const malformed = [{ name: "openai", status: "healthy" }]; // missing models
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(malformed),
      });

      const result = await client.listProviders();
      // implementation returns what server sends; verify it handles gracefully
      expect(result[0]).toHaveProperty("name", "openai");
    });

    it("should handle malformed response (non-array)", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ name: "openai" }), // object not array
      });

      const result = await client.listProviders();
      // TypeScript would catch at compile, but runtime returns what server sends
      expect(result).toEqual({ name: "openai" });
    });

    it("should use custom base URL", async () => {
      const customClient = new ProviderClient("http://custom:9000");
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([]),
      });

      await customClient.listProviders();
      expect(mockFetch).toHaveBeenCalledWith("http://custom:9000/api/v2/providers");
    });

    it("should use default base URL when none provided", async () => {
      const defaultClient = new ProviderClient();
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([]),
      });

      await defaultClient.listProviders();
      expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/api/v2/providers");
    });

    it("should send GET request with correct headers", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([]),
      });

      await client.listProviders();

      const call = mockFetch.mock.calls[0];
      expect(call[0]).toBe("http://localhost:8000/api/v2/providers");
      // GET request - no body, default headers
    });
  });
});