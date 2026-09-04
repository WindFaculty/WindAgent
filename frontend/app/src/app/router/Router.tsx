import { useState, useEffect } from "react";

export type AppRoute =
  | "workspace"
  | "studio"
  | "agents"
  | "model_gateway"
  | "automation"
  | "production"
  | "live_record"
  | "quality"
  | "operations";

export function useRouter(defaultRoute: AppRoute = "workspace") {
  const [currentRoute, setCurrentRoute] = useState<AppRoute>(() => {
    const hash = window.location.hash.replace(/^#\/?/, "") as AppRoute;
    const validRoutes: AppRoute[] = [
      "workspace",
      "studio",
      "agents",
      "model_gateway",
      "automation",
      "production",
      "live_record",
      "quality",
      "operations",
    ];
    return validRoutes.includes(hash) ? hash : defaultRoute;
  });

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace(/^#\/?/, "") as AppRoute;
      const validRoutes: AppRoute[] = [
        "workspace",
        "studio",
        "agents",
        "model_gateway",
        "automation",
        "production",
        "live_record",
        "quality",
        "operations",
      ];
      if (validRoutes.includes(hash)) {
        setCurrentRoute(hash);
      }
    };

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const navigate = (route: AppRoute) => {
    window.location.hash = `#/${route}`;
    setCurrentRoute(route);
  };

  return { currentRoute, navigate };
}
