/**
 * P1.7 — Production Feature Module Public API
 * Pre-production readiness gate + honest stage job history viewers.
 */
export { ProductionPage } from './pages/ProductionPage';
export type { ProductionTab } from './pages/ProductionPage';
export {
  useProductionPlan,
  useCreateProductionPlan,
  useShots,
  useCreateShot,
  useUpdateShot,
  useProductionJobs,
  useProductionJob,
  useSubmitStageJob,
  useCancelStageJob,
  useRetryStageJob,
  useDeliveryArtifact,
  useProductionRealtime,
  useProductionPreflight,
  usePackages,
  useFinalizePackage,
  productionKeys,
} from './hooks/useProduction';
export { ProductionReadiness } from './components/ProductionReadiness';
export { JobProgress } from './components/JobProgress';
export { JobFailure } from './components/JobFailure';
export { RetryAction } from './components/RetryAction';
export { ArtifactPreview } from './components/ArtifactPreview';
