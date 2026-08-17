/**
 * ProjectsPage tests — canonical ProjectsPage through real providers.
 * Server authority only: list/search via /api/v3/projects, create via POST /api/v3/projects.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { ProjectsPage } from '../pages/ProjectsPage';
import {
  cursorPage,
  jsonResponse,
  pathname,
  project,
  renderCanonical,
  type FetchFn,
} from './canonical';

const PROJECTS = [
  project('proj_1', 'Chú thỏ và cánh diều', 'Animation / Epic Saga'),
  project('proj_2', 'Cyberpunk Odyssey 2099', 'Cyberpunk / Sci-Fi'),
];

let fetchMock: ReturnType<typeof vi.fn<FetchFn>>;

beforeEach(() => {
  window.location.hash = '#/projects';
  fetchMock = vi.fn<FetchFn>(async (input: string | URL) => {
    const path = pathname(input);
    const url = new URL(String(input));
    if (path.endsWith('/api/v3/projects') && url.searchParams.has('search')) {
      const q = (url.searchParams.get('search') || '').toLowerCase();
      const filtered = PROJECTS.filter((p) => p.name.toLowerCase().includes(q));
      return jsonResponse(200, cursorPage(filtered));
    }
    if (path.endsWith('/api/v3/projects')) return jsonResponse(200, cursorPage(PROJECTS));
    if (path.endsWith('/api/v3/system/health')) return jsonResponse(200, { status: 'healthy' });
    if (path.endsWith('/api/v3/project-templates')) return jsonResponse(200, []);
    throw new Error(`unmocked URL: ${path}`);
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = '';
});

describe('ProjectsPage (canonical)', () => {
  it('renders projects from backend', async () => {
    renderCanonical(<ProjectsPage />);
    await waitFor(() => {
      expect(screen.getByText('Chú thỏ và cánh diều')).toBeInTheDocument();
    });
    expect(screen.getByText('Cyberpunk Odyssey 2099')).toBeInTheDocument();
  });

  it('filters projects dynamically by search term (server-side)', async () => {
    renderCanonical(<ProjectsPage />);
    await waitFor(() => {
      expect(screen.getByText('Cyberpunk Odyssey 2099')).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText('Tìm kiếm dự án theo tên hoặc mô tả...'), {
      target: { value: 'cánh diều' },
    });
    await waitFor(() => {
      expect(screen.getByText('Chú thỏ và cánh diều')).toBeInTheDocument();
      expect(screen.queryByText('Cyberpunk Odyssey 2099')).not.toBeInTheDocument();
    });
  });

  it('switches between Grid and List view mode', async () => {
    renderCanonical(<ProjectsPage />);
    await waitFor(() => {
      expect(screen.getByText('Chú thỏ và cánh diều')).toBeInTheDocument();
    });
    const listButton = screen.getByTitle('Xem dạng danh sách');
    fireEvent.click(listButton);
    await waitFor(() => {
      // List view renders table-like rows; both projects still visible
      expect(screen.getByText('Chú thỏ và cánh diều')).toBeInTheDocument();
      expect(screen.getByText('Cyberpunk Odyssey 2099')).toBeInTheDocument();
    });
  });

  it('opens creation modal and creates a new project', async () => {
    fetchMock.mockImplementation(async (input: string | URL, init?: RequestInit) => {
      const path = pathname(input);
      const url = new URL(String(input));
      if (path.endsWith('/api/v3/projects') && (!init || init.method !== 'POST')) {
        if (url.searchParams.has('search')) return jsonResponse(200, cursorPage([]));
        return jsonResponse(200, cursorPage(PROJECTS));
      }
      if (path.endsWith('/api/v3/projects') && init?.method === 'POST') {
        return jsonResponse(201, project('proj_new', 'Dự án mới'));
      }
      if (path.endsWith('/api/v3/system/health')) return jsonResponse(200, { status: 'healthy' });
      if (path.endsWith('/api/v3/project-templates')) return jsonResponse(200, []);
      throw new Error(`unmocked URL: ${path}`);
    });
    renderCanonical(<ProjectsPage />);
    await waitFor(() => {
      expect(screen.getByText('Chú thỏ và cánh diều')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo dự án mới' }));
    await waitFor(() => {
      expect(screen.getByText('Tên dự án')).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText('VD: Cyberpunk Odyssey 2099...'), {
      target: { value: 'Dự án mới' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo dự án' }));
    await waitFor(() => {
      expect(window.location.hash).toBe('#/projects/proj_new');
    });
  });

  it('handles backend offline or error state gracefully', async () => {
    fetchMock.mockImplementation(async (input: string | URL) => {
      const path = pathname(input);
      if (path.endsWith('/api/v3/projects')) throw new Error('network down');
      if (path.endsWith('/api/v3/system/health')) throw new Error('network down');
      if (path.endsWith('/api/v3/project-templates')) return jsonResponse(200, []);
      throw new Error(`unmocked URL: ${path}`);
    });
    renderCanonical(<ProjectsPage />);
    await waitFor(() => {
      expect(screen.getByText(/Lỗi tải danh sách dự án/)).toBeInTheDocument();
    });
  });
});