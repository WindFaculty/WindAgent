import React, { useState, useMemo } from 'react';
import { ProductionShell } from '@windagent/production-ui';
import { TauriDesktopAdapter } from '@windagent/production-platform';
import { FakeProductionApiClient, ProductionApiClient } from '@windagent/production-client';
import { ProductionRoute, ProductionPage } from '@windagent/production-contracts';

interface ProductionWorkspacePageProps {
  initialPage?: ProductionPage;
}

export const ProductionWorkspacePage: React.FC<ProductionWorkspacePageProps> = ({ initialPage = 'script' }) => {
  const [route, setRoute] = useState<ProductionRoute>({
    projectId: 'proj-alpha',
    page: initialPage,
  });

  const platformAdapter = useMemo(() => new TauriDesktopAdapter(), []);
  
  // Use FakeProductionApiClient as robust default for offline/mock desktop dev, fallback to HTTP if server active
  const apiClient = useMemo<ProductionApiClient>(() => {
    return new FakeProductionApiClient();
  }, []);

  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <ProductionShell
        platformAdapter={platformAdapter}
        apiClient={apiClient}
        route={route}
        onNavigate={(newRoute) => setRoute(newRoute)}
      />
    </div>
  );
};
