"""
Placeholder so the `external/` directory is tracked in git.

This directory is the recommended home for **vendored third-party
sources** that WindAgent integrates with but does not own.

Agent-S3 specifically:
  - Upstream:    https://github.com/simular-ai/Agent-S
  - PyPI name:   `gui-agents` (preferred install path)
  - Submodule:   optional, see scripts/setup_agent_s3.ps1

If you choose the **package** install mode (recommended), this directory
stays empty and `gui-agents` is pulled from PyPI into the backend venv
by `uv pip install "gui-agents==0.3.2"` (or the optional extra
`uv pip install ".[agent-s3]"`).

If you choose the **external clone** mode, populate this directory with:

    git clone https://github.com/simular-ai/Agent-S external/Agent-S

The `external/Agent-S/` checkout is then **imported lazily** by
`apps/backend/services/agent_s3_adapter.py` when
`WINDAGENT_AGENT_S3_SOURCE=external`. WindAgent never modifies files
inside the clone -- patches, if absolutely necessary, are tracked
separately in `artifacts/agent_s3_integration/patches/`.

See `docs/agent_s3_integration.md` for the full install / disable /
debug guide.
"""