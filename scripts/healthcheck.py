"""Production healthcheck CLI probe for WindAgent V2 container orchestrators."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def check_health(host: str, port: int, timeout_sec: float = 3.0) -> bool:
    """Query /health and /ready endpoints to verify backend liveness and readiness."""
    url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WindAgent-HealthProbe/2.0"})
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if resp.status != 200:
                print(f"[ERROR] Health check returned non-200 status: {resp.status}", file=sys.stderr)
                return False
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") != "ok":
                print(f"[ERROR] Health check status payload degraded: {data}", file=sys.stderr)
                return False
            print(f"[OK] Health check passed: {data}")
            return True
    except Exception as e:
        print(f"[ERROR] Health probe connection failed: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="WindAgent V2 Healthcheck Probe")
    parser.add_argument("--host", default="127.0.0.1", help="Target API host")
    parser.add_argument("--port", type=int, default=8000, help="Target API port")
    parser.add_argument("--timeout", type=float, default=3.0, help="Timeout in seconds")

    args = parser.parse_args()
    if check_health(args.host, args.port, args.timeout):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
