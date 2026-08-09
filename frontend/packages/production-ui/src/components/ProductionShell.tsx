import React, { useState, useEffect } from 'react';
import { ProductionPlatformAdapter } from '@windagent/production-platform';
import { ProductionApiClient } from '@windagent/production-client';
import { ProductionHeader } from './ProductionHeader';
import { ImportFileDialog } from './ImportFileDialog';
import { ScriptEditorPlaceholder } from './ScriptEditorPlaceholder';
import { AssetLibraryPlaceholder } from './AssetLibraryPlaceholder';
import { VideoWorkspacePlaceholder } from './VideoWorkspacePlaceholder';
import {
  ProductionRoute,
  ProductionPage,
  ProductionProject,
  ProductionRevision,
  SelectedFile,
} from '@windagent/production-contracts';

export interface ProductionShellProps {
  platformAdapter: ProductionPlatformAdapter;
  apiClient: ProductionApiClient;
  route: ProductionRoute;
  onNavigate: (route: ProductionRoute) => void;
}

export const ProductionShell: React.FC<ProductionShellProps> = ({
  platformAdapter,
  apiClient,
  route,
  onNavigate,
}) => {
  const [projects, setProjects] = useState<ProductionProject[]>([]);
  const [currentProject, setCurrentProject] = useState<ProductionProject | null>(null);
  const [currentRevision, setCurrentRevision] = useState<ProductionRevision | null>(null);
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [importedFiles, setImportedFiles] = useState<SelectedFile[]>([]);

  useEffect(() => {
    let isMounted = true;
    apiClient.listProjects().then((list) => {
      if (!isMounted) return;
      setProjects(list);
      if (route.projectId) {
        const found = list.find((p) => p.id === route.projectId);
        if (found) setCurrentProject(found);
      } else if (list.length > 0) {
        setCurrentProject(list[0]);
      }
    });

    if (route.projectId) {
      apiClient.getLatestRevision(route.projectId).then((rev) => {
        if (isMounted) setCurrentRevision(rev);
      });
    }

    return () => {
      isMounted = false;
    };
  }, [route.projectId, apiClient]);

  const handleSelectProject = (projectId: string) => {
    const nextRoute: ProductionRoute = {
      projectId,
      page: route.page || 'script',
    };
    onNavigate(nextRoute);
  };

  const handlePageTab = (page: ProductionPage) => {
    const nextRoute: ProductionRoute = {
      projectId: route.projectId || currentProject?.id || 'proj-alpha',
      page,
    };
    onNavigate(nextRoute);
  };

  return (
    <div className="production-shell" style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      width: '100%',
      background: '#0f1117',
      color: '#fff',
      fontFamily: 'Inter, system-ui, sans-serif'
    }}>
      {/* Header */}
      <ProductionHeader
        currentProject={currentProject}
        currentRevision={currentRevision}
        syncStatus="synced"
        backendStatus="online"
        availableProjects={projects}
        onSelectProject={handleSelectProject}
        onOpenImportDialog={() => setIsImportOpen(true)}
      />

      {/* Workspace Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Navigation Sidebar */}
        <nav style={{
          width: '220px',
          background: '#161922',
          borderRight: '1px solid #2d3139',
          padding: '16px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px'
        }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#6b7280', letterSpacing: '1px', paddingLeft: '8px', marginBottom: '8px' }}>
            Production Modules
          </div>

          <button
            onClick={() => handlePageTab('script')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '10px 12px',
              borderRadius: '6px',
              border: 'none',
              background: route.page === 'script' ? '#2563eb' : 'transparent',
              color: route.page === 'script' ? '#fff' : '#9ca3af',
              fontWeight: route.page === 'script' ? 600 : 400,
              cursor: 'pointer',
              textAlign: 'left'
            }}
          >
            📜 Script Editor
          </button>

          <button
            onClick={() => handlePageTab('assets')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '10px 12px',
              borderRadius: '6px',
              border: 'none',
              background: route.page === 'assets' ? '#2563eb' : 'transparent',
              color: route.page === 'assets' ? '#fff' : '#9ca3af',
              fontWeight: route.page === 'assets' ? 600 : 400,
              cursor: 'pointer',
              textAlign: 'left'
            }}
          >
            🎨 Asset Library
          </button>

          <button
            onClick={() => handlePageTab('video')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '10px 12px',
              borderRadius: '6px',
              border: 'none',
              background: route.page === 'video' ? '#2563eb' : 'transparent',
              color: route.page === 'video' ? '#fff' : '#9ca3af',
              fontWeight: route.page === 'video' ? 600 : 400,
              cursor: 'pointer',
              textAlign: 'left'
            }}
          >
            🎬 Video Workspace
          </button>

          {importedFiles.length > 0 && (
            <div style={{ marginTop: 'auto', background: '#252932', padding: '12px', borderRadius: '6px', fontSize: '12px' }}>
              <div style={{ color: '#60a5fa', fontWeight: 600, marginBottom: '6px' }}>Recent Imports:</div>
              {importedFiles.map((f) => (
                <div key={f.id} style={{ color: '#d1d5db', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  • {f.name}
                </div>
              ))}
            </div>
          )}
        </nav>

        {/* Content Area */}
        <main style={{ flex: 1, overflowY: 'auto' }}>
          {route.page === 'script' && (
            <ScriptEditorPlaceholder
              projectId={route.projectId || currentProject?.id || 'proj-alpha'}
              revisionId={currentRevision?.id}
              selectedEntityId={route.entityId}
            />
          )}
          {route.page === 'assets' && (
            <AssetLibraryPlaceholder
              projectId={route.projectId || currentProject?.id || 'proj-alpha'}
              revisionId={currentRevision?.id}
              selectedEntityId={route.entityId}
            />
          )}
          {route.page === 'video' && (
            <VideoWorkspacePlaceholder
              projectId={route.projectId || currentProject?.id || 'proj-alpha'}
              revisionId={currentRevision?.id}
              selectedEntityId={route.entityId}
            />
          )}
        </main>
      </div>

      {/* File Import Dialog */}
      <ImportFileDialog
        platformAdapter={platformAdapter}
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onFilesSelected={(files) => setImportedFiles((prev) => [...prev, ...files])}
      />
    </div>
  );
};
