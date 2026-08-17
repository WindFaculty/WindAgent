/**
 * Phase 9D — Reviews Feature Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '@windagent/app/src/shared/hooks/useApiClient';
import type { ReviewSubjectType, ReviewDecisionKind } from '@windagent/api-contracts';

export const reviewKeys = {
  all: ['reviews'] as const,
  list: (params?: object) => [...reviewKeys.all, 'list', params] as const,
  detail: (reviewId: string) => [...reviewKeys.all, 'detail', reviewId] as const,
  comments: (reviewId: string) => [...reviewKeys.all, 'comments', reviewId] as const,
};

export function useReviews(params?: { subject_type?: ReviewSubjectType; episode_id?: string; project_id?: string; status?: string }) {
  const client = useApiClient();
  return useQuery({
    queryKey: reviewKeys.list(params),
    queryFn: () => client.reviews.list(params),
  });
}

export function useReview(reviewId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: reviewKeys.detail(reviewId),
    queryFn: () => client.reviews.get(reviewId),
    enabled: Boolean(reviewId),
  });
}

export function useReviewComments(reviewId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: reviewKeys.comments(reviewId),
    queryFn: () => client.reviews.listComments(reviewId),
    enabled: Boolean(reviewId),
  });
}

export function useCreateReview() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { subject_type: ReviewSubjectType; subject_id: string; episode_id?: string; project_id?: string }) =>
      client.reviews.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reviewKeys.all });
    },
  });
}

export function useAddReviewComment(reviewId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { author: string; role?: string; text: string }) =>
      client.reviews.addComment(reviewId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reviewKeys.comments(reviewId) });
      queryClient.invalidateQueries({ queryKey: reviewKeys.detail(reviewId) });
    },
  });
}

export function useSubmitReviewDecision(reviewId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { decision: ReviewDecisionKind; revision_id: string; expected_version: number; reason?: string; decided_by: string }) =>
      client.reviews.submitDecision(reviewId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reviewKeys.detail(reviewId) });
      queryClient.invalidateQueries({ queryKey: reviewKeys.all });
    },
  });
}
