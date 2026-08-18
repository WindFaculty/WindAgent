/**
 * @vitest-environment happy-dom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  WebPlatformAdapter,
  createWebAdapter,
  TauriPlatformAdapter,
  createTauriAdapter,
} from '../platform';

describe('Phase 14 Platform Adapter & Capability Model', () => {
  describe('WebPlatformAdapter', () => {
    it('implements platform = "web" and kind = "web"', () => {
      const adapter = createWebAdapter();
      expect(adapter.kind).toBe('web');
      expect(adapter.platform).toBe('web');
    });

    it('reports truthful web capabilities', async () => {
      const adapter = new WebPlatformAdapter();
      const caps = await adapter.getSystemCapabilities();

      expect(caps.supportsNativeFilePicker).toBe(false);
      expect(caps.supportsSystemMetrics).toBe(false);
      expect(caps.supportsLocalRuntime).toBe(false);
      expect(caps.supportsDeepLinks).toBe(true);
    });

    it('provides valid simulated system metrics for dashboard/monitoring', async () => {
      const adapter = new WebPlatformAdapter();
      const metrics = await adapter.getSystemMetrics();

      expect(metrics.cpu).toBeGreaterThanOrEqual(0);
      expect(metrics.ram).toBeGreaterThanOrEqual(0);
      expect(metrics.ramTotalGb).toBe(16);
      expect(metrics.gpuName).toContain('Web GPU');
      expect(metrics.cpuHistory.length).toBeGreaterThan(0);
    });

    it('returns null for secure credentials and native file picker in web', async () => {
      const adapter = new WebPlatformAdapter();
      expect(await adapter.getSecureCredential('api_key')).toBeNull();
      expect(await adapter.selectFile()).toBeNull();
    });

    it('handles openExternal safely', async () => {
      const adapter = new WebPlatformAdapter();
      const windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

      await adapter.openExternal('https://example.com');
      expect(windowOpenSpy).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer');
      windowOpenSpy.mockRestore();
    });
  });

  describe('TauriPlatformAdapter', () => {
    it('implements platform = "desktop" and kind = "tauri"', () => {
      const adapter = createTauriAdapter();
      expect(adapter.kind).toBe('tauri');
      expect(adapter.platform).toBe('desktop');
    });

    it('reports full desktop capabilities', async () => {
      const adapter = new TauriPlatformAdapter();
      const caps = await adapter.getSystemCapabilities();

      expect(caps.supportsNativeFilePicker).toBe(true);
      expect(caps.supportsNativeNotifications).toBe(true);
      expect(caps.supportsSystemMetrics).toBe(true);
      expect(caps.supportsLocalRuntime).toBe(true);
      expect(caps.supportsDeepLinks).toBe(true);
    });

    it('provides system metrics gracefully when Tauri is not attached in dev', async () => {
      const adapter = new TauriPlatformAdapter();
      const metrics = await adapter.getSystemMetrics();

      expect(metrics.cpu).toBeGreaterThanOrEqual(0);
      expect(metrics.ram).toBeGreaterThanOrEqual(0);
      expect(metrics.cpuHistory.length).toBeGreaterThan(0);
    });

    it('bridges getNativeSystemMetrics when Tauri invoke is present', async () => {
      const adapter = new TauriPlatformAdapter();
      (window as any).__TAURI__ = {
        invoke: vi.fn().mockResolvedValue({
          cpu: 45.2,
          ram: 70.1,
          ram_gb: 11.2,
          ram_total_gb: 16.0,
          gpu: 55.0,
          gpu_name: 'RTX 4090',
          vram: 60.0,
          vram_gb: 14.4,
          vram_total_gb: 24.0,
        }),
      };

      const metrics = await adapter.getNativeSystemMetrics();
      expect(metrics.cpu).toBe(45);
      expect(metrics.ram).toBe(70);
      expect(metrics.gpuName).toBe('RTX 4090');
      delete (window as any).__TAURI__;
    });

    it('bridges selectFile when Tauri dialog is available', async () => {
      const adapter = new TauriPlatformAdapter();
      (window as any).__TAURI__ = {
        dialog: {
          open: vi.fn().mockResolvedValue('/path/to/selected/file.png'),
        },
      };

      const res = await adapter.selectFile({ multiple: false });
      expect(res).toBe('/path/to/selected/file.png');
      delete (window as any).__TAURI__;
    });

    it('bridges showNotification when Tauri notification is available', async () => {
      const adapter = new TauriPlatformAdapter();
      const sendNotification = vi.fn().mockResolvedValue(undefined);
      (window as any).__TAURI__ = {
        notification: {
          sendNotification,
        },
      };

      await adapter.showNotification('Build Complete', { body: 'Render finished' });
      expect(sendNotification).toHaveBeenCalledWith({
        title: 'Build Complete',
        body: 'Render finished',
      });
      delete (window as any).__TAURI__;
    });
  });
});
