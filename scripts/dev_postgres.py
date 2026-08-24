#!/usr/bin/env python
"""Cross-platform PostgreSQL-over-Docker driver for local development/tests.

One command surface around compose.yaml:

    python scripts/dev_postgres.py up                 # start + wait until pg_isready healthy
    python scripts/dev_postgres.py status             # container state + health
    python scripts/dev_postgres.py url [--db NAME]    # print the asyncpg URL
    python scripts/dev_postgres.py migrate [--db N]   # create DB if needed + Alembic to head
    python scripts/dev_postgres.py test [pytest...]   # ephemeral DB -> migrations -> attestation
                                                      #   -> pytest -> drop DB
    python scripts/dev_postgres.py down [--clean]     # stop stack (--clean also deletes volume)

Design rules:
  * Readiness is polled from `docker inspect` health (pg_isready), never by
    sleeping a fixed number of seconds.
  * The `test` command runs against an EPHEMERAL database that is dropped on
    success; on ANY failure the database and run evidence under
    artifacts/ci/dev-postgres/ are kept for inspection.
  * Credentials mirror the CI service containers (test:test/windagent) so local
    semantics match .github/workflows/ci.yaml exactly.
  * Migrations use the canonical programmatic runner (windagent_storage),
    never hand-written DDL or a hardcoded revision.
  * The backend identity gate (check_postgres_backend.py, server major 16,
    fail-closed) runs before pytest, exactly like CI.

Host-port precedence everywhere (wrapper URL and compose mapping share one
source of truth): `--port` flag > WINDAGENT_POSTGRES_PORT in the process
environment > WINDAGENT_POSTGRES_PORT in a repo-root `.env` > 55432. The
resolved port is injected into the docker compose subprocess so the published
mapping can never drift from the URL the wrapper dials.

Run with the repository virtualenv so windagent_storage/asyncpg are importable,
e.g.:  .venv\\Scripts\\python.exe scripts/dev_postgres.py test
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "compose.yaml"
DOT_ENV_FILE = ROOT / ".env"
CONTAINER_NAME = "windagent-postgres"
DEFAULT_HOST_PORT = 55432
DEV_DATABASE = "windagent"

HEALTH_TIMEOUT_S = 120.0
POLL_INTERVAL_S = 1.0

# Known Docker Desktop install locations (Windows) used when `docker` is not
# on PATH yet (fresh installs do not always update the current shell's PATH).
_DOCKER_KNOWN_PATHS = (
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
    str(
        Path(os.environ.get("LOCALAPPDATA", "."))
        / "Docker"
        / "Docker"
        / "resources"
        / "bin"
        / "docker.exe"
    ),
)

_DB_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested)
# --------------------------------------------------------------------------- #


def resolve_docker_exe() -> str:
    exe = shutil.which("docker")
    if exe:
        return exe
    for candidate in _DOCKER_KNOWN_PATHS:
        if Path(candidate).is_file():
            return candidate
    raise SystemExit(
        "ERROR: docker executable not found on PATH or in known install paths.\n"
        "Install Docker Desktop (WSL2 backend on Windows) and make sure it is running."
    )


def load_dot_env(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE reader for the compose-style repo-root `.env`.

    Comments (#), blank lines and surrounding quotes are stripped; values are
    never expanded or interpolated. Missing file yields {}.
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def effective_host_port(
    override: int | None = None,
    environ: Mapping[str, str] | None = None,
    dotenv: Mapping[str, str] | None = None,
) -> int:
    """Port precedence: --port > process environment > .env file > default."""
    if override is not None:
        return override
    merged = dict(dotenv or {})
    merged.update(environ or os.environ)
    raw = str(merged.get("WINDAGENT_POSTGRES_PORT", "")).strip()
    if raw:
        try:
            return int(raw)
        except ValueError as exc:
            raise SystemExit(
                f"ERROR: invalid WINDAGENT_POSTGRES_PORT={raw!r} (expected an integer)"
            ) from exc
    return DEFAULT_HOST_PORT


def build_async_url(host_port: int, database: str) -> str:
    """asyncpg URL with the CI-mirroring dev credentials (test:test)."""
    return f"postgresql+asyncpg://test:test@localhost:{host_port}/{database}"


def validate_db_name(name: str) -> str:
    if not _DB_NAME_RE.match(name):
        raise SystemExit(
            f"ERROR: invalid database name {name!r} "
            "(allowed: letters, digits, underscore; must not start with a digit)"
        )
    return name


def new_disposable_db_name() -> str:
    """Ephemeral database name, unique per run without colliding across shells."""
    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    return f"windagent_test_{stamp}_{os.getpid():05d}"


def summarize_pytest(text: str) -> str:
    """Extract the short pytest result summary ('N passed, M failed...')."""
    bordered = re.search(
        r"^\s*=+ .*?((?:\d+\s+\w+(?:,\s*)?)+) .*?=+\s*$", text, re.MULTILINE
    )
    if bordered:
        return bordered.group(1)
    # pytest -q emits an unbordered final line: '113 passed in 12.34s'.
    borderless = re.search(
        r"^\s*((?:\d+\s+\w+(?:,\s*)?)+)\s+in\s+[\d.:]+s\s*$", text, re.MULTILINE
    )
    return borderless.group(1) if borderless else "no summary line found"


def _attestation_command(
    python_exe: str, script_path: Path, out_path: Path
) -> list[str]:
    """CI-shaped invocation of the fail-closed backend identity gate.

    check_postgres_backend.py declares --output required=True and every CI job
    passes it (ci.yaml p1-e2e-postgres, postgres-production-semantics).
    """
    return [python_exe, str(script_path), "--output", str(out_path)]


# --------------------------------------------------------------------------- #
# Docker plumbing
# --------------------------------------------------------------------------- #


def _run_docker(
    args: Sequence[str], extra_env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [resolve_docker_exe(), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _port_env(host_port: int) -> dict[str, str]:
    """Pin compose's ${WINDAGENT_POSTGRES_PORT} to the wrapper-resolved port."""
    return {"WINDAGENT_POSTGRES_PORT": str(host_port)}


def container_health() -> str | None:
    """Health string from docker inspect, or None when the container is absent."""
    result = _run_docker(["inspect", "-f", "{{.State.Health.Status}}", CONTAINER_NAME])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def published_host_port() -> int | None:
    """The host port the running container actually publishes 5432 on."""
    template = '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}'
    result = _run_docker(["inspect", "-f", template, CONTAINER_NAME])
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _dump_postgres_logs(tail: int = 50) -> None:
    result = _run_docker(
        ["compose", "-f", str(COMPOSE_FILE), "logs", "--tail", str(tail), "postgres"]
    )
    sys.stdout.write(result.stdout[-4000:])
    sys.stderr.write(result.stderr[-1000:])


def wait_until_healthy(timeout_s: float = HEALTH_TIMEOUT_S) -> float:
    """Poll container health until 'healthy'; raise with logs on timeout."""
    started = time.monotonic()
    deadline = started + timeout_s
    last_seen = ""
    while time.monotonic() < deadline:
        status = container_health()
        printable = status or "not_created"
        if printable != last_seen:
            print(f"      health: {printable}")
            last_seen = printable
        if status == "healthy":
            return time.monotonic() - started
        time.sleep(POLL_INTERVAL_S)
    print("ERROR: postgres did not become healthy in time. Container logs:")
    _dump_postgres_logs()
    raise SystemExit(f"ERROR: no healthy postgres within {timeout_s:.0f}s")


def ensure_running(host_port: int | None = None) -> float:
    """Start (or reconcile) the compose postgres; return seconds waited.

    When a host port is given and the running container publishes a different
    one (e.g. started earlier with another --port), the container is recreated
    with the requested mapping so the published port can never drift from the
    URLs the wrapper builds.
    """
    extra_env = _port_env(host_port) if host_port is not None else None
    needs_recreate = False
    if container_health() == "healthy":
        published = published_host_port()
        if host_port is None or published is None or published == host_port:
            return 0.0
        print(
            f"      container maps host port {published}; "
            f"recreating for requested {host_port}"
        )
        needs_recreate = True
    cmd = ["compose", "-f", str(COMPOSE_FILE), "up", "-d"]
    if needs_recreate:
        cmd.append("--force-recreate")
    cmd.append("postgres")
    result = _run_docker(cmd, extra_env=extra_env)
    if result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(
            f"ERROR: docker compose up failed (exit {result.returncode}). "
            "Is the Docker engine running?"
        )
    return wait_until_healthy()


# --------------------------------------------------------------------------- #
# Database lifecycle inside the cluster
# --------------------------------------------------------------------------- #


def ensure_database(host_port: int, database: str) -> str:
    import asyncpg

    async def _run() -> str:
        conn = await asyncpg.connect(
            host="127.0.0.1",
            port=host_port,
            user="test",
            password="test",
            database=DEV_DATABASE,
            timeout=10,
        )
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", database
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{database}"')
                return "created"
            return "already exists"
        finally:
            await conn.close()

    return asyncio.run(_run())


def drop_database(host_port: int, database: str) -> str:
    import asyncpg

    async def _run() -> str:
        conn = await asyncpg.connect(
            host="127.0.0.1",
            port=host_port,
            user="test",
            password="test",
            database=DEV_DATABASE,
            timeout=10,
        )
        try:
            # WITH (FORCE) terminates lingering connections first (PG13+).
            await conn.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
            return "dropped"
        finally:
            await conn.close()

    return asyncio.run(_run())


def drop_database_quietly(host_port: int, database: str) -> bool:
    try:
        outcome = drop_database(host_port, database)
        print(f"      {outcome} ephemeral database '{database}'")
        return True
    except Exception as exc:  # noqa: BLE001
        first = str(exc).splitlines()[0][:120] if str(exc) else ""
        print(
            f"      WARNING: could not drop '{database}': "
            f"{type(exc).__name__}: {first}"
        )
        return False


def _keep_db_hint(database: str, async_url: str) -> None:
    print(f"      database '{database}' KEPT for inspection; connect: {async_url}")
    print(f"      drop it later: python scripts/dev_postgres.py psql-drop --db {database}")


# --------------------------------------------------------------------------- #
# Migrations + backend identity
# --------------------------------------------------------------------------- #


def _migration_runner():
    try:
        from windagent_storage.migrations import runner
    except ModuleNotFoundError:
        sys.path.insert(0, str(ROOT / "storage"))
        from windagent_storage.migrations import runner
    return runner


def run_migrations(async_url: str) -> str:
    """Alembic upgrade to head via the canonical runner, then verify the head."""
    runner = _migration_runner()
    runner.alembic_upgrade_head(async_url)
    current = tuple(runner.alembic_current(async_url))
    heads = tuple(runner.alembic_heads())
    if current != heads:
        raise SystemExit(
            f"ERROR: alembic current {current or '(empty)'} != heads {heads}"
        )
    return ",".join(current)


def run_backend_attestation(env: Mapping[str, str], out_path: Path) -> tuple[int, str]:
    """Run scripts/verification/check_postgres_backend.py (fail-closed, PG16)."""
    script = ROOT / "scripts" / "verification" / "check_postgres_backend.py"
    proc = subprocess.run(
        _attestation_command(sys.executable, script, out_path),
        cwd=ROOT,
        env=dict(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout + proc.stderr


# --------------------------------------------------------------------------- #
# Run bookkeeping
# --------------------------------------------------------------------------- #


def _new_run_dir(database: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    safe_db = re.sub(r"[^A-Za-z0-9_-]", "_", database)[:40]
    return ROOT / "artifacts" / "ci" / "dev-postgres" / f"{stamp}_{safe_db}"


def _write_run_json(run_dir: Path, payload: Mapping[str, object]) -> None:
    (run_dir / "run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _stream_to_file(cmd: Sequence[str], env: Mapping[str, str], log_path: Path) -> int:
    """Run cmd with output teed into log_path; stream nothing to the console."""
    with log_path.open("wb") as sink:
        process = subprocess.Popen(  # noqa: S603
            list(cmd),
            cwd=ROOT,
            env=dict(env),
            stdout=sink,
            stderr=subprocess.STDOUT,
        )
        try:
            return process.wait()
        except KeyboardInterrupt:
            process.kill()
            raise


def _read_log(log_path: Path) -> str:
    return log_path.read_text(encoding="utf-8", errors="replace")


def _print_log_tail(log_path: Path, lines: int = 25) -> None:
    tail = _read_log(log_path).splitlines()[-lines:]
    for line in tail:
        print(f"      | {line}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_up(args: argparse.Namespace) -> int:
    port = effective_host_port(
        args.port, dotenv=load_dot_env(DOT_ENV_FILE)
    )
    print(f"[up] postgres via compose (host port {port})")
    waited = ensure_running(port)
    if waited == 0.0:
        print("[ok] already healthy")
    else:
        print(f"[ok] healthy after {waited:.1f}s")
    print(f"url: {build_async_url(port, DEV_DATABASE)}")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    result = _run_docker(
        [
            "inspect",
            "-f",
            "{{.State.Status}} health={{if .State.Health}}"
            "{{.State.Health.Status}}{{else}}none{{end}}",
            CONTAINER_NAME,
        ]
    )
    if result.returncode != 0:
        print("STATUS: not_created")
        return 0
    print(f"STATUS: {result.stdout.strip()}")
    return 0


def cmd_url(args: argparse.Namespace) -> int:
    validate_db_name(args.db)
    port = effective_host_port(args.port, dotenv=load_dot_env(DOT_ENV_FILE))
    print(build_async_url(port, args.db))
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    validate_db_name(args.db)
    port = effective_host_port(args.port, dotenv=load_dot_env(DOT_ENV_FILE))
    async_url = build_async_url(port, args.db)
    waited = ensure_running(port)
    if waited:
        print(f"[migrate] waited {waited:.1f}s for healthy postgres")
    state = ensure_database(port, args.db)
    head = run_migrations(async_url)
    print(f"[ok] database '{args.db}' {state}; alembic head={head}")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    port = effective_host_port(args.port, dotenv=load_dot_env(DOT_ENV_FILE))
    database = args.db or new_disposable_db_name()
    validate_db_name(database)
    async_url = build_async_url(port, database)
    run_dir = _new_run_dir(database)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Evidence collected so far; written into run.json even on mid-run crashes.
    payload: dict[str, object] = {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "database": database,
        "host_port": port,
    }
    db_live = False  # once true, failures must KEEP the database

    try:
        print(f"[1/5] postgres up (host port {port})")
        waited = ensure_running(port)
        if waited:
            print(f"      healthy after {waited:.1f}s")

        print(f"[2/5] ephemeral database '{database}'")
        print(f"      {ensure_database(port, database)}")
        db_live = True

        print("[3/5] alembic upgrade to head")
        head = run_migrations(async_url)
        payload["alembic_head"] = head
        print(f"      head={head}")

        env = dict(os.environ)
        env["WINDAGENT_TEST_POSTGRES_URL"] = async_url
        env["WINDAGENT_DATABASE_URL"] = async_url
        # The pytest child writes into a redirected handle; force UTF-8 so the
        # log is encoding-stable regardless of the host ANSI code page.
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        print("[4/5] backend identity attestation (expect server major 16)")
        att_out_path = run_dir / "postgres_backend.json"
        att_rc, att_out = run_backend_attestation(env, att_out_path)
        payload["attestation_rc"] = att_rc
        att_lines = [ln for ln in att_out.splitlines() if ln.strip()]
        if att_lines:
            print(f"      {att_lines[-1]}")
        if att_rc != 0:
            _write_run_json(run_dir, {**payload, "pytest_rc": None})
            print(f"[FAIL] backend attestation rc={att_rc}")
            print(f"log: {att_out_path}")
            _keep_db_hint(database, async_url)
            return att_rc
        print("[ok] backend is real PostgreSQL 16")

        if args.pytest_args:
            pytest_cmd = [sys.executable, "-m", "pytest", *args.pytest_args]
            selection = " ".join(args.pytest_args)
        else:
            pytest_cmd = [sys.executable, "-m", "pytest", "-m", "postgres"]
            selection = "-m postgres"
        print(f"[5/5] pytest {selection}")
        print(f"      (full output -> {run_dir / 'pytest.log'})")
        started = time.monotonic()
        rc = _stream_to_file(pytest_cmd, env, run_dir / "pytest.log")
        duration = time.monotonic() - started
        summary = summarize_pytest(_read_log(run_dir / "pytest.log"))
        _write_run_json(
            run_dir,
            {
                **payload,
                "pytest_rc": rc,
                "duration_s": round(duration, 1),
                "summary": summary,
            },
        )

        if rc == 0:
            print(f"[pass] {summary} ({duration:.0f}s)")
            _print_log_tail(run_dir / "pytest.log")
            print(f"log: {run_dir / 'pytest.log'}")
            if args.skip_drop:
                print(f"[keep] database '{database}' left in place (--skip-drop)")
                print(f"       connect: {async_url}")
            else:
                drop_database_quietly(port, database)
            return 0

        print(f"[FAIL] {summary} ({duration:.0f}s) — pytest exit {rc}")
        _print_log_tail(run_dir / "pytest.log")
        print(f"log: {run_dir / 'pytest.log'}")
        _keep_db_hint(database, async_url)
        return rc

    except (Exception, SystemExit) as exc:  # noqa: BLE001 — evidence before exit
        code = getattr(exc, "code", 1)
        if not isinstance(code, int):
            code = 1
        first = str(exc).splitlines()[0][:200] if str(exc) else ""
        print(f"[FAIL] {type(exc).__name__}: {first}")
        payload["error"] = f"{type(exc).__name__}: {first}"
        payload.setdefault("alembic_head", None)
        _write_run_json(run_dir, {**payload, "pytest_rc": None})
        if db_live:
            _keep_db_hint(database, async_url)
        else:
            drop_database_quietly(port, database)
        return code


def cmd_psql_drop(args: argparse.Namespace) -> int:
    validate_db_name(args.db)
    port = effective_host_port(args.port, dotenv=load_dot_env(DOT_ENV_FILE))
    ok = drop_database_quietly(port, args.db)
    return 0 if ok else 1


def cmd_down(args: argparse.Namespace) -> int:
    cmd = ["compose", "-f", str(COMPOSE_FILE), "down"]
    if args.clean:
        cmd.append("-v")
    result = _run_docker(cmd)
    if result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode or 1
    tail = [ln for ln in result.stdout.splitlines() if ln.strip()][-5:]
    for line in tail:
        print(f"      {line}")
    print("[ok] stack stopped" + (" and volume deleted" if args.clean else ""))
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dev_postgres",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="start the compose postgres and wait until healthy")
    up.add_argument("--port", type=int, default=None, help="host port override")
    up.set_defaults(func=cmd_up)

    status = sub.add_parser("status", help="print container state and health")
    status.set_defaults(func=cmd_status)

    url_p = sub.add_parser("url", help="print the asyncpg URL for a database")
    url_p.add_argument("--db", default=DEV_DATABASE)
    url_p.add_argument("--port", type=int, default=None)
    url_p.set_defaults(func=cmd_url)

    mig = sub.add_parser(
        "migrate", help="create the database if needed and run Alembic to head"
    )
    mig.add_argument("--db", default=DEV_DATABASE)
    mig.add_argument("--port", type=int, default=None)
    mig.set_defaults(func=cmd_migrate)

    test_p = sub.add_parser(
        "test",
        help="ephemeral DB -> migrations -> attestation -> pytest -> drop",
    )
    test_p.add_argument("--db", default=None, help="override disposable database name")
    test_p.add_argument("--port", type=int, default=None)
    test_p.add_argument(
        "--skip-drop", action="store_true", help="keep the database even on success"
    )
    test_p.add_argument(
        "pytest_args",
        nargs="*",
        help=(
            "extra pytest arguments; when given they REPLACE the default "
            "'-m postgres' selection (use `--` before option-style args)"
        ),
    )
    test_p.set_defaults(func=cmd_test)

    drop_p = sub.add_parser("psql-drop", help="drop one database created by `test`")
    drop_p.add_argument("--db", required=True)
    drop_p.add_argument("--port", type=int, default=None)
    drop_p.set_defaults(func=cmd_psql_drop)

    down = sub.add_parser("down", help="stop the compose stack")
    down.add_argument(
        "--clean", action="store_true", help="also delete the data volume"
    )
    down.set_defaults(func=cmd_down)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:  # pragma: no cover - argparse required=True guards this
        build_parser().error("a subcommand is required")
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
