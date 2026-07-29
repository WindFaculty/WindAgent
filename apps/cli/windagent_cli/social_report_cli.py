"""Dedicated command-line entrypoint for social browser reporting."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Optional, Sequence

from windagent_cli.social_report import execute_social_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="windagent-social-report",
        description=(
            "Collect public or user-authorized Facebook, YouTube, and TikTok pages "
            "with agent-browser and produce a Qwen + Gemma + Gemini report."
        ),
    )
    parser.add_argument("--query", required=True, help="Research question")
    parser.add_argument(
        "--url",
        dest="urls",
        action="append",
        required=True,
        help="Social page URL; repeat for multiple sources",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/social_research",
        help="Workspace-relative report directory",
    )
    parser.add_argument(
        "--local-model",
        default="qwen3.5",
        help="Installed Ollama model ID used for structured extraction",
    )
    parser.add_argument(
        "--gemma-model",
        default="gemma-4-31b",
        help="Google API model ID used for independent synthesis",
    )
    parser.add_argument(
        "--gemini-model",
        default="gemini-3.5-flash-lite",
        help="Google API model ID used for verification synthesis",
    )
    parser.add_argument(
        "--browser-session-prefix",
        default="windagent-social",
        help="Prefix for isolated agent-browser sessions",
    )
    parser.add_argument(
        "--browser-profile",
        help="Chrome profile name/path copied by agent-browser for authorized access",
    )
    parser.add_argument(
        "--browser-state",
        help="Saved agent-browser state file; must not be committed",
    )
    parser.add_argument(
        "--authenticated",
        action="store_true",
        help=(
            "Use preflight URL containment because agent-browser native domain "
            "containment is incompatible with profile/state restore"
        ),
    )
    parser.add_argument(
        "--skip-model-preflight",
        action="store_true",
        help="Skip provider model discovery checks",
    )
    parser.add_argument(
        "--no-screenshots",
        action="store_true",
        help="Do not save full-page evidence screenshots",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code in (0, None) else 3

    try:
        result = asyncio.run(
            execute_social_report(
                query=args.query,
                urls=args.urls,
                output_dir=args.output_dir,
                local_model=args.local_model,
                gemma_model=args.gemma_model,
                gemini_model=args.gemini_model,
                browser_session_prefix=args.browser_session_prefix,
                browser_profile=args.browser_profile,
                browser_state=args.browser_state,
                authenticated=args.authenticated,
                skip_model_preflight=args.skip_model_preflight,
                save_screenshots=not args.no_screenshots,
            )
        )
    except Exception as exc:
        payload = {
            "error": f"{type(exc).__name__}: {exc}",
            "data_source": "LIVE",
            "non_production": False,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {payload['error']}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=== WindAgent Social Browser Report ===")
        print(f"Status: {result['status']}")
        print(
            f"Sources: {result['successful_source_count']}/{result['source_count']}"
        )
        print(f"Markdown: {result['markdown_path']}")
        print(f"JSON: {result['json_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
