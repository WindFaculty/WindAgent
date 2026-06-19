import type { RunnerSnapshot } from "../state/sessionStore";

interface Props {
  runner: RunnerSnapshot;
  hasSession: boolean;
  busy: boolean;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onRetry: () => void;
}

export function ControlBar({
  runner,
  hasSession,
  busy,
  onPause,
  onResume,
  onStop,
  onRetry,
}: Props) {
  const taskDone = runner.kind === "running" ? runner.state.task_done : true;
  const paused = runner.kind === "running" ? runner.state.paused : false;
  const hasFailedStep =
    runner.kind === "running" && runner.state.last_failed_step_id !== null;

  const disableAll = !hasSession || busy;
  const disablePause = disableAll || taskDone || paused;
  const disableResume = disableAll || taskDone || !paused;
  const disableStop = disableAll || taskDone;
  const disableRetry = disableAll || !taskDone || !hasFailedStep;

  return (
    <div className="control-bar">
      <button onClick={onPause} disabled={disablePause} title="Tạm dừng workflow">
        Pause
      </button>
      <button onClick={onResume} disabled={disableResume} title="Tiếp tục">
        Resume
      </button>
      <button onClick={onStop} disabled={disableStop} title="Hủy workflow">
        Stop
      </button>
      <button onClick={onRetry} disabled={disableRetry} title="Chạy lại step failed">
        Retry
      </button>
    </div>
  );
}