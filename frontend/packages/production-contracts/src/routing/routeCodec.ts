import { ProductionRoute, ProductionPage } from '../types';

export class ProductionRouteCodec {
  static parseRoute(pathOrUrl: string): ProductionRoute | null {
    try {
      const url = new URL(pathOrUrl, 'http://localhost');
      const parts = url.pathname.split('/').filter(Boolean);

      // Expected path format: /production/:projectId/:page
      if (parts[0] !== 'production' || !parts[1]) {
        return null;
      }

      const projectId = decodeURIComponent(parts[1]);
      const rawPage = parts[2] || 'script';
      const page: ProductionPage = ['script', 'assets', 'video'].includes(rawPage)
        ? (rawPage as ProductionPage)
        : 'script';

      const entityId = url.searchParams.get('entityId') || url.searchParams.get('entity') || undefined;
      const revisionId = url.searchParams.get('revisionId') || url.searchParams.get('revision') || undefined;
      const sceneId = url.searchParams.get('sceneId') || url.searchParams.get('scene') || undefined;
      const entityType = (url.searchParams.get('entityType') as ProductionRoute['entityType']) || undefined;
      const assetId = url.searchParams.get('assetId') || url.searchParams.get('asset') || undefined;
      const requirementId = url.searchParams.get('requirementId') || url.searchParams.get('requirement') || undefined;
      const resolutionAction = (url.searchParams.get('resolutionAction') || url.searchParams.get('action')) as ProductionRoute['resolutionAction'] || undefined;

      return {
        projectId,
        page,
        entityId: entityId ? decodeURIComponent(entityId) : undefined,
        revisionId: revisionId ? decodeURIComponent(revisionId) : undefined,
        sceneId: sceneId ? decodeURIComponent(sceneId) : undefined,
        entityType,
        assetId: assetId ? decodeURIComponent(assetId) : undefined,
        requirementId: requirementId ? decodeURIComponent(requirementId) : undefined,
        resolutionAction,
      };
    } catch {
      return null;
    }
  }

  static stringifyRoute(route: ProductionRoute): string {
    const encodedProject = encodeURIComponent(route.projectId);
    let path = `/production/${encodedProject}/${route.page}`;

    const params = new URLSearchParams();
    if (route.entityId) params.set('entityId', route.entityId);
    if (route.revisionId) params.set('revisionId', route.revisionId);
    if (route.sceneId) params.set('sceneId', route.sceneId);
    if (route.entityType) params.set('entityType', route.entityType);
    if (route.assetId) params.set('assetId', route.assetId);
    if (route.requirementId) params.set('requirementId', route.requirementId);
    if (route.resolutionAction) params.set('resolutionAction', route.resolutionAction);

    const queryString = params.toString();
    if (queryString) {
      path += `?${queryString}`;
    }

    return path;
  }
}
