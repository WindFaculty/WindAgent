#!/usr/bin/env python3
"""Fail-closed runtime import and version smoke check."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    errors: list[str] = []
    results: dict[str, object] = {}
    try:
        from windagent_core.version import PRODUCT_VERSION
    except ImportError as exc:
        PRODUCT_VERSION = None
        errors.append(f"windagent_core.version import failed: {exc}")

    for distribution in (
        "windagent-core",
        "windagent-api",
        "windagent-cli",
        "windagent-worker",
    ):
        try:
            installed = version(distribution)
            results[f"{distribution}_version"] = installed
            if PRODUCT_VERSION is not None and installed != PRODUCT_VERSION:
                errors.append(
                    f"{distribution} {installed} != {PRODUCT_VERSION}"
                )
        except PackageNotFoundError:
            errors.append(f"{distribution} is not installed")

    try:
        from windagent_api.main import app

        results["api_version"] = app.version
        if PRODUCT_VERSION is not None and app.version != PRODUCT_VERSION:
            errors.append(
                f"FastAPI version {app.version} != {PRODUCT_VERSION}"
            )
    except Exception as exc:
        errors.append(
            f"windagent_api runtime import failed: "
            f"{type(exc).__name__}: {exc}"
        )

    try:
        import windagent_worker

        worker_version = getattr(windagent_worker, "__version__", None)
        results["worker_version"] = worker_version
        if worker_version is None:
            errors.append("windagent_worker has no __version__")
        elif PRODUCT_VERSION is not None and worker_version != PRODUCT_VERSION:
            errors.append(
                f"Worker version {worker_version} != {PRODUCT_VERSION}"
            )
    except ImportError as exc:
        errors.append(f"windagent_worker import failed: {exc}")

    cli = subprocess.run(
        [sys.executable, "-m", "windagent_cli", "--version", "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    results["cli_returncode"] = cli.returncode
    results["cli_stdout"] = cli.stdout.strip()
    if cli.returncode != 0:
        errors.append(
            f"CLI version command exited {cli.returncode}: "
            f"{cli.stderr.strip()}"
        )
    elif PRODUCT_VERSION is not None:
        try:
            cli_data = json.loads(cli.stdout)
        except json.JSONDecodeError as exc:
            errors.append(f"CLI version output is not JSON: {exc}")
        else:
            if cli_data.get("product_version") != PRODUCT_VERSION:
                errors.append(
                    "CLI product_version "
                    f"{cli_data.get('product_version')!r} != "
                    f"{PRODUCT_VERSION!r}"
                )

    report = {
        "product_version": PRODUCT_VERSION,
        "results": results,
        "errors": errors,
        "verdict": "PASS" if not errors else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
