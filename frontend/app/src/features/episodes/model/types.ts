/**
 * Canonical Episode Model Types & Pipeline Stages (Phase 8).
 */

export type {
  EpisodeResource,
  EpisodeDetail,
  EpisodeArtifactEnvelope,
  PipelineRun,
  CursorPage,
} from '@windagent/api-contracts';

export type CheckpointStage =
  | 'IDEA'
  | 'STORY_BIBLE'
  | 'OUTLINE'
  | 'SCREENPLAY'
  | 'REVIEW'
  | 'LOCKED'
  | 'READY_FOR_PRODUCTION';

export interface CheckpointStepInfo {
  id: CheckpointStage;
  label: string;
  shortLabel: string;
  description: string;
  order: number;
}

export const CHECKPOINT_STEPS: CheckpointStepInfo[] = [
  {
    id: 'IDEA',
    label: 'Khám Phá Ý Tưởng',
    shortLabel: 'Ý tưởng',
    description: 'Sinh và tuyển chọn tiền đề, chủ đề và hướng đi cốt truyện.',
    order: 1,
  },
  {
    id: 'STORY_BIBLE',
    label: 'Kinh Thánh Cốt Truyện',
    shortLabel: 'Story Bible',
    description: 'Thiết lập nhân vật, luật lệ thế giới và quy tắc vũ trụ.',
    order: 2,
  },
  {
    id: 'OUTLINE',
    label: 'Dàn Ý Phân Cảnh',
    shortLabel: 'Dàn ý',
    description: 'Xây dựng nhịp kịch bản theo hồi, phân đoạn và cao trào.',
    order: 3,
  },
  {
    id: 'SCREENPLAY',
    label: 'Kịch Bản Chi Tiết',
    shortLabel: 'Kịch bản',
    description: 'Bản thảo kịch bản hoàn chỉnh gồm bối cảnh, hành động và hội thoại.',
    order: 4,
  },
  {
    id: 'REVIEW',
    label: 'Duyệt & Đánh Giá',
    shortLabel: 'Duyệt',
    description: 'Kiểm duyệt chất lượng, gửi phản hồi sửa đổi trước khi khóa.',
    order: 5,
  },
  {
    id: 'LOCKED',
    label: 'Khóa Kịch Bản Sản Xuất',
    shortLabel: 'Khóa kịch bản',
    description: 'Kịch bản đã chốt bất biến với mã băm sha-256 sẵn sàng cho Storyboard & Video.',
    order: 6,
  },
];

export function getStageProgress(stage: string): number {
  const s = String(stage || '').toUpperCase();
  switch (s) {
    case 'LOCKED':
    case 'READY_FOR_PRODUCTION':
      return 100;
    case 'REVIEW':
      return 85;
    case 'SCREENPLAY_REVIEW':
      return 70;
    case 'REVISING':
      return 60;
    case 'SCREENPLAY':
      return 70;
    case 'OUTLINE_REVIEW':
      return 50;
    case 'OUTLINE':
      return 50;
    case 'STORY_BIBLE_REVIEW':
      return 30;
    case 'STORY_BIBLE':
      return 30;
    case 'IDEA_REVIEW':
      return 15;
    case 'IDEA':
      return 15;
    case 'DRAFT':
      return 5;
    case 'FAILED':
    case 'CANCELLED':
      return 0;
    default:
      return 5;
  }
}

/** Map canonical EpisodeState to Vietnamese label + colors (no mock buckets) */
export function getEpisodeStateMeta(state: string): { label: string; bg: string; color: string; border: string; dot: string } {
  const s = String(state || '').toUpperCase();
  switch (s) {
    case 'READY_FOR_PRODUCTION':
      return { label: 'Sẵn sàng sản xuất', bg: 'rgba(34,197,94,0.14)', color: '#4ade80', border: 'rgba(34,197,94,0.28)', dot: '#22c55e' };
    case 'LOCKED':
      return { label: 'Đã khóa', bg: 'rgba(34,197,94,0.14)', color: '#4ade80', border: 'rgba(34,197,94,0.28)', dot: '#22c55e' };
    case 'SCREENPLAY_REVIEW':
      return { label: 'Chờ duyệt kịch bản', bg: 'rgba(59,130,246,0.14)', color: '#60a5fa', border: 'rgba(59,130,246,0.30)', dot: '#3b82f6' };
    case 'OUTLINE_REVIEW':
      return { label: 'Chờ duyệt dàn ý', bg: 'rgba(245,158,11,0.14)', color: '#fbbf24', border: 'rgba(245,158,11,0.30)', dot: '#f59e0b' };
    case 'STORY_BIBLE_REVIEW':
      return { label: 'Chờ duyệt Story Bible', bg: 'rgba(168,85,247,0.14)', color: '#c084fc', border: 'rgba(168,85,247,0.30)', dot: '#a855f7' };
    case 'IDEA_REVIEW':
      return { label: 'Chờ duyệt ý tưởng', bg: 'rgba(56,189,248,0.14)', color: '#38bdf8', border: 'rgba(56,189,248,0.28)', dot: '#0ea5e9' };
    case 'REVISING':
      return { label: 'Đang chỉnh sửa', bg: 'rgba(245,158,11,0.14)', color: '#fbbf24', border: 'rgba(245,158,11,0.30)', dot: '#f59e0b' };
    case 'FAILED':
      return { label: 'Thất bại', bg: 'rgba(239,68,68,0.14)', color: '#f87171', border: 'rgba(239,68,68,0.28)', dot: '#ef4444' };
    case 'CANCELLED':
      return { label: 'Đã hủy', bg: 'rgba(100,116,139,0.14)', color: '#94a3b8', border: 'rgba(100,116,139,0.24)', dot: '#64748b' };
    case 'DRAFT':
    default:
      return { label: 'Bản nháp', bg: 'rgba(100,116,139,0.14)', color: '#94a3b8', border: 'rgba(100,116,139,0.24)', dot: '#64748b' };
  }
}

export function getProgressColor(progress: number): string {
  if (progress >= 100) return '#22c55e';
  if (progress >= 70) return '#3b82f6';
  if (progress >= 50) return '#f59e0b';
  if (progress >= 30) return '#a78bfa';
  if (progress >= 15) return '#38bdf8';
  return '#5b6478';
}
