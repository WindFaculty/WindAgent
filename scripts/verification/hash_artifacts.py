#!/usr/bin/env python3
"""
Hash Artifacts (Phase 2)

Computes SHA256 hashes for all artifact files in a directory.
Outputs artifact_hashes JSON mapping.
"""

from __future__ import annotations
import json
import sys
import hashlib
import argparse
from pathlib import Path
from typing import Dict


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_artifacts(directory: Path, pattern: str = "*.json", recursive: bool = False) -> Dict[str, str]:
    """Hash all artifact files matching pattern."""
    if recursive:
        files = directory.rglob(pattern)
    else:
        files = directory.glob(pattern)
    
    hashes = {}
    for filepath in files:
        if filepath.is_file():
            rel_path = filepath.relative_to(directory)
            hashes[str(rel_path)] = compute_file_hash(filepath)
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description="Hash artifact files")
    parser.add_argument("--directory", "-d", required=True, help="Directory containing artifacts")
    parser.add_argument("--pattern", "-p", default="*.json", help="File pattern to match")
    parser.add_argument("--recursive", "-r", action="store_true", help="Recursive search")
    parser.add_argument("--output", "-o", help="Output JSON file (default: stdout)")
    
    args = parser.parse_args()
    
    directory = Path(args.directory)
    if not directory.exists():
        print(f"ERROR: Directory does not exist: {directory}", file=sys.stderr)
        return 1
    
    hashes = hash_artifacts(directory, args.pattern, args.recursive)
    
    output = json.dumps(hashes, indent=2)
    
    if args.output:
        Path(args.output).write_text(output)
        print(f"Hashes written to {args.output}")
    else:
        print(output)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())