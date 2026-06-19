import { useTheme } from "../state/theme";

interface Props {
  modelsOnline: boolean | null;
  hasSession: boolean;
  error: string | null;
}

export function StatusBar({ modelsOnline, hasSession, error }: Props) {
  const { theme, toggle } = useTheme();
  const themeLabel = theme === "dark" ? "Switch to light" : "Switch to dark";
  return (
    <header className="status-bar">
      <span className="title">WindAgent</span>
      <span className="spacer" />
      <span className="status-item">
        Model:{" "}
        {modelsOnline === null ? (
          <em className="muted">checking...</em>
        ) : modelsOnline ? (
          <strong className="ok">ready</strong>
        ) : (
          <strong className="warn">offline</strong>
        )}
      </span>
      <span className="status-item">
        Session: {hasSession ? <strong>active</strong> : <em className="muted">none</em>}
      </span>
      {error && <span className="status-item error">{error}</span>}
      <button
        type="button"
        className="theme-toggle"
        onClick={toggle}
        title={themeLabel}
        aria-label={themeLabel}
      >
        {theme === "dark" ? "☀" : "☾"}
      </button>
    </header>
  );
}