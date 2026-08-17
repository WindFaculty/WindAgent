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
  switch (stage) {
    case 'LOCKED':
    case 'READY_FOR_PRODUCTION':
      return 100;
    case 'REVIEW':
      return 85;
    case 'SCREENPLAY':
      return 70;
    case 'OUTLINE':
      return 50;
    case 'STORY_BIBLE':
      return 30;
    case 'IDEA':
      return 15;
    default:
      return 5;
  }
}
