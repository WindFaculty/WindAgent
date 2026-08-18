/**
 * Web Application Entry Point (Phase 14 Web/Desktop Convergence).
 * Zero @desktop coupling. Uses shared @windagent/app and styles.
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { App as SharedApp, bootstrapFrontend } from "@windagent/app";
import { platform } from "./platform";
import "@windagent/app/styles.css";

bootstrapFrontend({ platform });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <SharedApp platform={platform} />
  </React.StrictMode>
);
