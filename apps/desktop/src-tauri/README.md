# Phase 6 — Tauri scaffold placeholder.

Requires Rust toolchain to actually build (`rustup`, `cargo`, MSVC Build Tools on Windows). When Tauri 2 is set up:

```bash
# Install Rust + Tauri CLI (one-time)
# https://tauri.app/start/prerequisites/
rustup-init -y
cargo install tauri-cli --version "^2.0"

# Run the desktop shell (auto-builds the React app too)
cargo tauri dev

# Production build
cargo tauri build
```

The frontend (`apps/desktop/src/`) is plain React + Vite + TypeScript and
can also run standalone:

```bash
cd apps/desktop
npm install
npm run dev      # http://localhost:5173, proxies /api + /ws to backend
```

See `apps/desktop/README.md` for full instructions.