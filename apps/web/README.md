# WindAgent Standalone Web Application (`apps/web`)

Standalone React + Vite Web Application for WindAgent Architecture V2.
Decoupled from Desktop shell (`apps/desktop`). Both Web and Desktop share the production build outputs from `apps/web`.

## Features
- **Frontend Architecture**: `features/`, `entities/`, `shared/`, `app/`, `clients/`, `state/`
- **Decoupled Clients**: API Client, Event Stream Client, Artifact Client, Permission Client, Provider Client
- **State Recovery**: Refresh recovery, event reconnect & deduplication, pending permission restoration, task history persistence, worker disconnection state handler.
