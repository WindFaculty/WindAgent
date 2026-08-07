# FFmpeg Safety & Subprocess Policy

## 1. Tool Boundary & Invocation Standard

To ensure security, determinism, and system stability, all FFmpeg and ffprobe executions MUST follow these strict rules:

1. **Argv Execution Only**: Commands must be invoked as an explicit argument vector (`list[str]`). Shell string interpolation (e.g. `shell=True` or bash string concatenations) is strictly forbidden.
2. **Version Pinning**: The exact binary path, version number, and build flags of `ffmpeg` and `ffprobe` must be recorded in every render receipt.
3. **Workspace Path Containment**: Input and output file paths must reside strictly within authorized workspace directories or the artifact store (`artifacts/video_production/...`). Paths targeting system root, temporary dirs outside workspace, or relative traversal paths (`..`) are rejected.
4. **No Arbitrary LLM Scripts**: Custom filter scripts generated directly by LLMs or external prompts must not be executed raw. Filter graphs must be constructed deterministically by typed domain assembly planners (`AssemblyPlanner`).

## 2. Process Lifecycle & Resource Controls

1. **Timeout & Execution Limits**: Every FFmpeg process must run under a strict timeout (default: 300 seconds for assembly, 30 seconds for verification probing).
2. **Process Tree Termination**: If a process times out or receives a cancellation signal, the executor must kill the entire subprocess tree to prevent orphan background jobs.
3. **Log Sanitization & Redaction**: Subprocess stdout/stderr logs must be sanitized before recording. Any secret keys, tokens, or environment credentials detected in logs are redacted.

## 3. Quarantine & Fail-Closed Behavior

1. **Validation Pre-checks**: If any input clip is missing, zero-byte, un-probeable, or corrupted, the render job immediately fails closed without attempting assembly.
2. **Quarantine Storage**: Intermediate files from failed render jobs must be isolated in a quarantine store (`artifacts/video_production/quarantine/`) and never published as valid deliverables.
3. **Receipt Generation**: Every command execution (successful or failed) generates a structured `FfmpegCommandReceipt` containing invocation timestamp, return code, execution time, stdout/stderr snippets, and SHA-256 hashes of inputs and outputs.
