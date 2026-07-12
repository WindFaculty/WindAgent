# ADR 0004: Isolated Git Worktree for Coding Agents

## Status
Accepted

## Context
When multiple coding agents run in parallel, they will overwrite each other's changes if they share the same working directory. Furthermore, editing the user's primary working directory directly makes it impossible to discard changes easily, run regression tests on separate branches, or review changes safely before integration.

## Decision
We will isolate each coding agent session into its own Git worktree.

### 1. Worktree Directory Structure
Worktrees will be created under the `.windagent` metadata folder of the repository:
```
<repo-root>/.windagent/worktrees/<conversation-id>/<agent-instance-id>/
```

### 2. Branch and Lifecycle Mapping
- Every coding task assigned to a sub-agent will spawn a dedicated Git branch:
  ```
  windagent/<conversation-id>/<task-id>/<agent-instance-id>
  ```
- The backend will issue a `git worktree add <path> -b <branch-name>` command.
- The agent session will run with the working directory set to this isolated path.
- Upon task completion, the worktree is unlinked, but branch history is preserved for recovery or auditing.

### 3. Agent Capabilities & Sandboxing
Within their worktrees, coding agents can:
- Read, create, and modify codebase files.
- Run local compilers, formatters, linters, and unit tests.
- Create local commits.

Coding agents are strictly prohibited from:
- Editing files in the primary repository workspace.
- Directly pushing branches to remote repositories, merging to main, or executing force pushes.
- Altering branch permissions.

### 4. Integration Flow
Once coding tasks are complete:
1. **Test Agent** runs validations inside each worktree.
2. **Review Agent** generates a code diff and executes architectural checks.
3. **Integration Agent** merges or cherry-picks the validated branches into the main workspace.
4. Full regression tests are run on the integrated code.
5. In case of merge conflicts, the integration manager raises an event for human intervention.

### 5. Worktree Retention Policy
Worktrees corresponding to failed or canceled tasks are kept in a quarantine state for a retention period (e.g., 24 hours) rather than deleted immediately, allowing developers to inspect logs, local code status, and uncommitted edits.

## Consequences
- **Concurrency**: Multiple coding agents can run, build, and test concurrently without race conditions.
- **Safety**: Unfinished or failing agent changes do not corrupt the developer's active workspace.
- **Clean Git History**: Changes are organized into modular, short-lived feature branches before integration.
