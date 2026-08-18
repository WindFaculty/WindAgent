/**
 * Desktop Application Root (Phase 14 Web/Desktop Convergence).
 * Delegates 100% to @windagent/app SharedApp with Tauri platform adapter.
 */

import { useMemo } from "react";
import { App as SharedApp, createTauriAdapter } from "@windagent/app";

export function App() {
  const platform = useMemo(() => createTauriAdapter(), []);
  return <SharedApp platform={platform} />;
}

export default App;
