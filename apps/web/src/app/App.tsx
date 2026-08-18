/**
 * Web App Wrapper (Phase 14 Web/Desktop Convergence).
 * Zero @desktop dependency.
 */

import React from "react";
import { App as SharedApp, createWebAdapter } from "@windagent/app";
import "@windagent/app/styles.css";

export const App: React.FC = () => {
  return <SharedApp platform={createWebAdapter()} />;
};
