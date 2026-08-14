import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ProjectsPage } from '../pages/ProjectsPage';

type FetchFn = (input: string | URL, init?: RequestInit) => Promise<Response>;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function sampleSeries(id: string, title: string, description = '', episodeCount = 0) {
  return {
    id,
    title,
    description,
    created_at: '2026-02-01T10:00:00Z',
    updated_at: '2026-02-01T10:00:00Z',
    episode_count: episodeCount,
  };
}

const CAPABILITIES = {
  capabilities: [
    { name: 'durable_db', status: 'AVAILABLE', reason: 'db' },
    { name: 'studio_orchestration', status: 'AVAILABLE', reason: 'seam' },
    { name: 'story_engine', status: 'AVAILABLE', reason: 'A5' },
    { name: 'worker', status: 'AVAILABLE', reason: 'none' },
    { name: 'model_route', status: 'AVAILABLE', reason: 'route' },
  ],
  fail_closed_flags: [],
  certification_mode: false,
};

let fetchMock: ReturnType<typeof vi.fn<FetchFn>>;

beforeEach(() => {
  window.location.hash = '#/projects';
  fetchMock = vi.fn<FetchFn>(async (input: string | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method || 'GET';

    if (url.endsWith('/api/v3/studio/capabilities')) {
      return jsonResponse(200, CAPABILITIES);
    }

    if (url.endsWith('/api/v3/studio/series') && method === 'GET') {
      return jsonResponse(200, {
        items: [
          sampleSeries('srs_alpha', 'Alpha Horizon', 'Hành trình vượt không gian vũ trụ bí ẩn.', 3),
          sampleSeries('srs_beta', 'Bóng Tối Thành Phố', 'Trinh thám siêu nhiên trong lòng đô thị cổ.', 0),
        ],
      });
    }

    if (url.endsWith('/api/v3/studio/series') && method === 'POST') {
      const body = JSON.parse(String(init?.body || '{}'));
      return jsonResponse(201, {
        series_id: 'srs_new_123',
        title: body.title,
        description: body.description,
        series_url: '/api/v3/studio/series/srs_new_123',
      });
    }

    if (url.includes('/api/v3/studio/series/srs_alpha/episodes') && method === 'POST') {
      const body = JSON.parse(String(init?.body || '{}'));
      return jsonResponse(201, {
        episode_id: 'ep_new_456',
        series_id: 'srs_alpha',
        title: body.title,
        episode_url: '/api/v3/studio/episodes/ep_new_456',
      });
    }

    if (url.includes('/api/v3/studio/series/srs_new_123/episodes') && method === 'POST') {
      const body = JSON.parse(String(init?.body || '{}'));
      return jsonResponse(201, {
        episode_id: 'ep_new_789',
        series_id: 'srs_new_123',
        title: body.title,
        episode_url: '/api/v3/studio/episodes/ep_new_789',
      });
    }

    if (url.includes('/episodes') && method === 'GET') {
      return jsonResponse(200, { items: [] });
    }

    if (url.includes('/api/v3/studio/series/srs_alpha') && method === 'GET') {
      return jsonResponse(200, sampleSeries('srs_alpha', 'Alpha Horizon', 'Hành trình vượt không gian vũ trụ bí ẩn.', 4));
    }

    if (url.includes('/api/v3/studio/series/srs_new_123') && method === 'GET') {
      return jsonResponse(200, sampleSeries('srs_new_123', 'Vũ Trụ Vô Tận', '', 1));
    }

    throw new Error(`unmocked URL: ${method} ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = '';
});

describe('ProjectsPage (Redesigned & Dynamic)', () => {
  it('renders dynamic series from backend and displays KPI metrics', async () => {
    render(<ProjectsPage />);

    expect(await screen.findByText('Alpha Horizon')).toBeInTheDocument();
    expect(screen.getByText('Bóng Tối Thành Phố')).toBeInTheDocument();
    expect(screen.getByText('Hành trình vượt không gian vũ trụ bí ẩn.')).toBeInTheDocument();

    // Check KPI items
    expect(screen.getByText('Tổng Số Dự Án')).toBeInTheDocument();
    expect(screen.getByText('Tổng Số Tập Phim')).toBeInTheDocument();
    expect(screen.getByText('Online / DB Sẵn Sàng')).toBeInTheDocument();
  });

  it('filters projects dynamically by search term', async () => {
    render(<ProjectsPage />);
    expect(await screen.findByText('Alpha Horizon')).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText(/Tìm kiếm theo tên/);
    fireEvent.change(searchInput, { target: { value: 'Bóng Tối' } });

    expect(screen.queryByText('Alpha Horizon')).not.toBeInTheDocument();
    expect(screen.getByText('Bóng Tối Thành Phố')).toBeInTheDocument();
  });

  it('switches between Grid and List view mode', async () => {
    render(<ProjectsPage />);
    expect(await screen.findByText('Alpha Horizon')).toBeInTheDocument();

    const listBtn = screen.getByTitle(/Chế độ danh sách/);
    fireEvent.click(listBtn);

    // List view has table headers
    expect(screen.getByText('Tên Dự Án')).toBeInTheDocument();
    expect(screen.getByText('Thể Loại')).toBeInTheDocument();
    expect(screen.getByText('Thao Tác')).toBeInTheDocument();
  });

  it('opens creation modal and creates a new series with episode', async () => {
    render(<ProjectsPage />);
    expect(await screen.findByText('Alpha Horizon')).toBeInTheDocument();

    const createBtn = screen.getByRole('button', { name: /Tạo Dự Án Mới/ });
    fireEvent.click(createBtn);

    expect(screen.getByText('Khởi Tạo Dự Án Mới')).toBeInTheDocument();

    const titleInput = screen.getByPlaceholderText(/Ví dụ: Rừng Xanh Kỳ Diệu/);
    fireEvent.change(titleInput, { target: { value: 'Vũ Trụ Vô Tận' } });

    const epTitleInput = screen.getByPlaceholderText(/Ví dụ: Tập 01: Khởi Đầu Mới/);
    fireEvent.change(epTitleInput, { target: { value: 'Tập 1: Xuất Phát' } });

    const submitBtn = screen.getByRole('button', { name: /^Tạo Dự Án$/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v3/studio/series'),
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('Vũ Trụ Vô Tận'),
        })
      );
    });
  });

  it('opens quick add episode modal and creates episode for selected series', async () => {
    render(<ProjectsPage />);
    expect(await screen.findByText('Alpha Horizon')).toBeInTheDocument();

    const addEpButtons = screen.getAllByTitle(/Thêm tập phim mới/);
    fireEvent.click(addEpButtons[0]);

    expect(screen.getByText('Thêm Tập Phim Mới')).toBeInTheDocument();

    const epTitleInput = screen.getByPlaceholderText(/Ví dụ: Tập 02: Cuộc Đào Tẩu/);
    fireEvent.change(epTitleInput, { target: { value: 'Tập 4: Bí Mật Sao Hỏa' } });

    const submitBtn = screen.getByRole('button', { name: /Thêm Tập Phim/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v3/studio/series/srs_alpha/episodes'),
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('Tập 4: Bí Mật Sao Hỏa'),
        })
      );
    });
  });

  it('handles backend offline or error state gracefully', async () => {
    fetchMock.mockImplementation(async () => {
      return jsonResponse(503, {
        type: 'about:blank',
        title: 'Service Unavailable',
        status: 503,
        detail: 'Studio service is offline',
        code: 'NETWORK_ERROR',
      });
    });

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText('Thử Lại')).toBeInTheDocument();
    });
  });
});
