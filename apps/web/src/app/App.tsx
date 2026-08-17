import React from "react";
import { App as SharedApp, createWebAdapter } from "@windagent/app";
import "@desktop/styles.css";

export const App: React.FC = () => {
  return <SharedApp platform={createWebAdapter()} />;
};
