import React, { lazy, useMemo } from "react";
import { App as SharedApp, createTauriAdapter, type RouteDescriptor, useUIStore, MonitoringPage, ProjectDetailPage, EpisodeWorkspacePage } from "@windagent/app";



import { MultiAgentProvider } from "./state/multiAgentStore";

function lazyNamed<T extends React.ComponentType<any>>(
  factory: () => Promise<any>,
  name: string
) {
  return lazy(() => factory().then((module) => ({ default: module[name] as T })));
}

const Dashboard = lazyNamed(() => import("./pages/Dashboard"), "Dashboard");
const Agents = lazyNamed(() => import("./pages/Agents"), "Agents");
const Models = lazyNamed(() => import("./pages/Models"), "Models");
const Endpoints = lazyNamed(() => import("./pages/Endpoints"), "Endpoints");
const Memory = lazyNamed(() => import("./pages/Memory"), "Memory");
const Workflows = lazyNamed(() => import("./pages/Workflows"), "Workflows");
const Browser = lazyNamed(() => import("./pages/Browser"), "Browser");
const Files = lazyNamed(() => import("./pages/Files"), "Files");
const Router = lazyNamed(() => import("./pages/Router"), "Router");
const Settings = lazyNamed(() => import("./pages/Settings"), "Settings");
const MultiAgentWorkspace = lazyNamed(() => import("./pages/MultiAgentWorkspace"), "MultiAgentWorkspace");
const AssetWorkspace = lazyNamed(() => import("./components/assets/AssetWorkspace"), "AssetWorkspace");
const ProductionWorkspacePage = lazyNamed(() => import("./pages/ProductionWorkspacePage"), "ProductionWorkspacePage");
const StudioPage = lazyNamed(() => import("./pages/StudioPage"), "StudioPage");
const CharactersPage = lazyNamed(() => import("./pages/CharactersPage"), "CharactersPage");
const EpisodesPage = lazyNamed(() => import("./pages/EpisodesPage"), "EpisodesPage");
const StoryBoardPage = lazyNamed(() => import("./pages/StoryBoardPage"), "StoryBoardPage");
const ProjectsPage = lazyNamed(() => import("./pages/ProjectsPage"), "ProjectsPage");
const ReviewsPage = lazyNamed(() => import("./pages/ReviewsPage"), "ReviewsPage");

export function App() {
  const platform = useMemo(() => createTauriAdapter(), []);
  const { conversationId } = useUIStore();

  const renderDesktopRoute = (route: RouteDescriptor, _params: Record<string, string>) => {
    switch (route.id) {
      case "dashboard":
        return <Dashboard />;
      case "monitoring":
        return <MonitoringPage />;
      case "agents":
        return <Agents setActiveTab={() => {}} />;

      case "models-library":
        return <Models setActiveTab={() => {}} />;
      case "models-endpoints":
        return <Endpoints />;
      case "memory":
        return <Memory setActiveTab={() => {}} />;
      case "workflows":
        return <Workflows />;
      case "browser":
        return <Browser />;
      case "files":
        return <Files />;
      case "workspace":
        return (
          <MultiAgentProvider conversationId={conversationId}>
            <MultiAgentWorkspace conversationId={conversationId} />
          </MultiAgentProvider>
        );
      case "router":
        return <Router />;
      case "studio":
        return <StudioPage />;
      case "projects":
        return <ProjectsPage />;
      case "project-detail":
        return <ProjectDetailPage projectId={_params.projectId} />;
      case "episodes":
        return <EpisodesPage />;
      case "episode-workspace":
        return <EpisodeWorkspacePage episodeId={_params.episodeId} />;
      case "storyboard":

        return <StoryBoardPage />;
      case "characters":
        return <CharactersPage />;
      case "reviews":
        return <ReviewsPage />;
      case "assets":
        return <AssetWorkspace />;
      case "production-script":
        return <ProductionWorkspacePage initialPage="script" />;
      case "production-assets":
        return <ProductionWorkspacePage initialPage="assets" />;
      case "production-video":
        return <ProductionWorkspacePage initialPage="video" />;
      case "settings":
        return <Settings />;
      default:
        return null;
    }
  };

  return <SharedApp platform={platform} customRouteRenderer={renderDesktopRoute} />;
}
