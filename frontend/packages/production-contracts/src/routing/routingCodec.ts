import { ProductionRoute } from '../types';

export function encodeProductionRoute(route: ProductionRoute): string {
  const basePath = `/production/${encodeURIComponent(route.projectId)}/${route.page}`;
  const queryParams = new URLSearchParams();

  if (route.revisionId) queryParams.set('revision', route.revisionId);
  if (route.sceneId) queryParams.set('scene', route.sceneId);
  if (route.entityId) queryParams.set('entity', route.entityId);
  if (route.entityType) queryParams.set('entityType', route.entityType);
  if (route.assetId) queryParams.set('asset', route.assetId);
  if (route.requirementId) queryParams.set('requirement', route.requirementId);
  if (route.resolutionAction) queryParams.set('action', route.resolutionAction);

  const queryString = queryParams.toString();
  return queryString ? `${basePath}?${queryString}` : basePath;
}

export function decodeProductionRoute(pathname: string, search: string): ProductionRoute {
  const parts = pathname.split('/').filter(Boolean);
  const projectId = parts[1] || 'default_project';
  const pageStr = parts[2] || 'script';
  const page = pageStr === 'assets' ? 'assets' : pageStr === 'video' ? 'video' : 'script';

  const params = new URLSearchParams(search);

  return {
    projectId,
    page,
    revisionId: params.get('revision') || undefined,
    sceneId: params.get('scene') || undefined,
    entityId: params.get('entity') || undefined,
    entityType: (params.get('entityType') as ProductionRoute['entityType']) || undefined,
    assetId: params.get('asset') || undefined,
    requirementId: params.get('requirement') || undefined,
    resolutionAction: (params.get('action') as ProductionRoute['resolutionAction']) || undefined,
  };
}
