#!/usr/bin/env python3
"""CLI utility for Hermes subprocess to proxy browser automation commands to WindAgent backend."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8765/api/v1"


def call_api(path: str, data: dict = None) -> dict:
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    req_data = json.dumps(data).encode("utf-8") if data is not None else None
    
    req = urllib.request.Request(url, data=req_data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        try:
            detail = json.loads(err_msg).get("detail", err_msg)
        except Exception:
            detail = err_msg
        print(f"API Error ({e.code}): {detail}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Connection Error: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="WindAgent Browser Bridge Proxy for Hermes")
    parser.add_argument("action", choices=["navigate", "click", "type", "back", "forward", "reload", "state"])
    parser.add_argument("session_id", help="WindAgent session UUID")
    parser.add_argument("args", nargs="*", help="Action specific arguments")

    args = parser.parse_args()
    session_id = args.session_id
    action = args.action

    if action == "navigate":
        if not args.args:
            print("Error: navigate action requires a URL", file=sys.stderr)
            sys.exit(1)
        url = args.args[0]
        res = call_api(f"/sessions/{session_id}/browser/navigate", {"url": url})
        print(f"Navigated successfully to: {res.get('url')} (Title: {res.get('title')})")

    elif action == "click":
        # Supports click <session_id> <x> <y> OR click <session_id> <selector>
        payload = {}
        if len(args.args) >= 2:
            try:
                payload["x"] = int(args.args[0])
                payload["y"] = int(args.args[1])
            except ValueError:
                payload["selector"] = args.args[0]
        elif len(args.args) == 1:
            payload["selector"] = args.args[0]
        else:
            print("Error: click action requires x, y coordinates or selector", file=sys.stderr)
            sys.exit(1)

        res = call_api(f"/sessions/{session_id}/browser/click", payload)
        print(f"Clicked page successfully. New URL: {res.get('url')}")

    elif action == "type":
        if not args.args:
            print("Error: type action requires text to type", file=sys.stderr)
            sys.exit(1)
        text = args.args[0]
        selector = args.args[1] if len(args.args) > 1 else None
        res = call_api(f"/sessions/{session_id}/browser/type", {"text": text, "selector": selector})
        print("Typed text successfully.")

    elif action == "back":
        res = call_api(f"/sessions/{session_id}/browser/back", {})
        print(f"Navigated back. Current URL: {res.get('url')}")

    elif action == "forward":
        res = call_api(f"/sessions/{session_id}/browser/forward", {})
        print(f"Navigated forward. Current URL: {res.get('url')}")

    elif action == "reload":
        res = call_api(f"/sessions/{session_id}/browser/reload", {})
        print(f"Reloaded page. Current URL: {res.get('url')}")

    elif action == "state":
        res = call_api(f"/sessions/{session_id}/browser")
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
