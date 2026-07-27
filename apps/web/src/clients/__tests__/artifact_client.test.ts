/**
 * Tests for ArtifactClient - Artifact listing client.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

global.fetch = vi.fn();

const mockFetch = global.fetch as vi.Mock;

vi.mock("../artifact_client", () => {
  return {
    ArtifactClient: class ArtifactClient {
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
    },
  };
});

import { ArtifactClient } from "../artifact_client";

interface ArtifactMeta {
  artifact_id: string;
  name: string;
  mime_type: string;
  size_bytes: number;
}

describe("ArtifactClient", () => {
  let client: ArtifactClient;

  beforeEach(() => {
    vi.clearAllMocks();
    client = new ArtifactClient("http://localhost:8000");
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe("listArtifacts", () => {
    it("should list artifacts successfully", async () => {
      const mockArtifacts: ArtifactMeta[] = [
        { artifact_id: "art-1", name: "output.txt", mime_type: "text/plain", size_bytes: 1024 },
        { artifact_id: "art-2", name: "result.json", mime_type: "application/json", size_bytes: 2048 },
      ];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockArtifacts),
      });

      const result = await client.listArtifacts();

      expect(result).toEqual(mockArtifacts);
      expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/api/v2/artifacts");
    });

    it("should return empty array when no artifacts", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([]),
      });

      const result = await client.listArtifacts();
      expect(result).toEqual([]);
    });

    it("should throw on HTTP error", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        statusText: "Internal Server Error",
      });

      await expect(client.listArtifacts()).rejects.toThrow(
        "Artifact fetch error: Internal Server Error"
      );
    });

    it("should throw on network error", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Network error"));

      await expect(client.listArtifacts()).rejects.toThrow("Network error");
    });

    it("should handle different mime types", async () => {
      const artifacts: ArtifactMeta[] = [
        { artifact_id: "a1", name: "img.png", mime_type: "image/png", size_bytes: 5000 },
        { artifact_id: "a2", name: "data.csv", mime_type: "text/csv", size_bytes: 3000 },
        { artifact_id: "a3", name: "binary.bin", mime_type: "application/octet-stream", size_bytes: 8000 },
      ];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(artifacts),
      });

      const result = await client.listArtifacts();
      expect(result[0].mime_type).toBe("image/png");
      expect(result[1].mime_type).toBe("text/csv");
      expect(result[2].mime_type).toBe("application/octet-stream");
    });

    it("should handle large file sizes", async () => {
      const artifacts: ArtifactMeta[] = [
        { artifact_id: "large", name: "big-file.zip", mime_type: "application/zip", size_bytes: 1024 * 1024 * 100 },
      ];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(artifacts),
      });

      const result = await client.listArtifacts();
      expect(result[0].size_bytes).toBe(1024 * 1024 * 100);
    });
  });
});