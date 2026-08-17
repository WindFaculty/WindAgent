import { describe, it, expect } from 'vitest';
import { ProjectCard } from '../components/ProjectCard';
import { ProjectList } from '../components/ProjectList';
import { ProjectFilters } from '../components/ProjectFilters';
import { CreateProjectDialog } from '../components/CreateProjectDialog';
import { CreateEpisodeDialog } from '../components/CreateEpisodeDialog';
import { ProjectTemplatePicker } from '../components/ProjectTemplatePicker';
import { ProjectsPage } from '../pages/ProjectsPage';
import { ProjectDetailPage } from '../pages/ProjectDetailPage';
import { useProjects, PROJECTS_QUERY_KEY } from '../hooks/useProjects';
import { useProject, PROJECT_QUERY_KEY, PROJECT_EPISODES_QUERY_KEY } from '../hooks/useProject';
import { useCreateProject } from '../hooks/useCreateProject';
import { useCreateEpisode } from '../hooks/useCreateEpisode';
import { useProjectTemplates, PROJECT_TEMPLATES_QUERY_KEY } from '../hooks/useProjectTemplates';
import { useCapabilities, CAPABILITIES_QUERY_KEY } from '../hooks/useCapabilities';
import { getCoverDesign, COVER_GRADIENTS } from '../model/types';

describe('Projects Feature Package (Phase 7)', () => {
  it('exports all project components and hooks properly', () => {
    expect(ProjectCard).toBeDefined();
    expect(ProjectList).toBeDefined();
    expect(ProjectFilters).toBeDefined();
    expect(CreateProjectDialog).toBeDefined();
    expect(CreateEpisodeDialog).toBeDefined();
    expect(ProjectTemplatePicker).toBeDefined();
    expect(ProjectsPage).toBeDefined();
    expect(ProjectDetailPage).toBeDefined();
    expect(useProjects).toBeDefined();
    expect(useProject).toBeDefined();
    expect(useCreateProject).toBeDefined();
    expect(useCreateEpisode).toBeDefined();
    expect(useProjectTemplates).toBeDefined();
    expect(useCapabilities).toBeDefined();
  });

  it('generates consistent gradient cover designs for projects', () => {
    const cover1 = getCoverDesign('proj-01', 'Cyberpunk');
    const cover2 = getCoverDesign('proj-01', 'Cyberpunk');
    expect(cover1).toEqual(cover2);
    expect(COVER_GRADIENTS).toContainEqual(cover1);
  });

  it('defines canonical query keys', () => {
    expect(PROJECTS_QUERY_KEY).toEqual(['v3', 'projects']);
    expect(PROJECT_QUERY_KEY('p1')).toEqual(['v3', 'projects', 'p1']);
    expect(PROJECT_EPISODES_QUERY_KEY('p1')).toEqual(['v3', 'projects', 'p1', 'episodes']);
    expect(PROJECT_TEMPLATES_QUERY_KEY).toEqual(['v3', 'project-templates']);
    expect(CAPABILITIES_QUERY_KEY).toEqual(['v3', 'studio', 'capabilities']);
  });
});
