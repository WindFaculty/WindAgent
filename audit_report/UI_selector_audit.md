# UI selector audit (req: agent selector picks sub-agent, not session)

VERDICT: claim PARTLY TRUE for dead code, FALSE for live path.

## Live path (App.tsx:441 -> MultiAgentWorkspace)
- Selector = sub-agent card onClick -> store.select(agentId) (MultiAgentWorkspace:417,
  multiAgentStore.select:78-85). Sets selectedAgentId ONLY. No session switch.
- Terminal = real WS terminal_output per selected agent (multiAgentStore:202-205,
  termLines:280). Inspector switches (selected:276).
- => selector picks sub-agent, not session. Claim FALSE on live UI.

## Dead component (AgentWorkspace.tsx) — still in repo, NOT mounted
- App.tsx mounts MultiAgentWorkspace only (441). AgentWorkspace.tsx never rendered.
- In dead code: selector = agent_type dropdown (coder/planner/researcher/browser/gui),
  onChange -> setSelectedAgentId (70-88). useAgentSession(agentId) -> ensureSession()
  -> createSession(agentId) -> NEW backend session per agent_type
  (useAgentSession.ts:30-36). So selecting dropdown = create new session, not pick
  sub-agent instance. Matches user claim.
- Dead code terminal = chat messages split by newline (AgentWorkspace.tsx:35-37) ->
  FAKE terminal from chat (violates req #20).
- Dead code = old single-agent model (user picks Coder/Planner directly) -> violates
  req #1 (orchestrator-only chat).

## Other (Agents.tsx)
- selectedAgentId default "coder", setSelectedAgentId -> fetchAgentActivity (35,94,101,
  125,379). This is agent-runtime activity page, selector = agent instance not session.
  Not workspace. Out of scope.

## Conclusion
Live workspace selector correct (picks sub-agent). User-claimed bug lives in DEAD
AgentWorkspace.tsx (unmounted) = proof old anti-pattern exists in tree but not live.
Recommend delete AgentWorkspace.tsx to avoid confusion + revive of wrong pattern.
Severity: LOW (live), MEDIUM (dead code debt).
