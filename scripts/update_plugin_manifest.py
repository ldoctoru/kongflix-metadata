#!/usr/bin/env python3
"""Add or replace a version entry in the Jellyfin plugin repository manifest."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--guid", required=True, help="Plugin guid the version belongs to")
    parser.add_argument("--version", required=True, help="4-part assembly version, e.g. 1.0.1.0")
    parser.add_argument("--target-abi", required=True)
    parser.add_argument("--changelog", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--checksum", required=True, help="MD5 checksum of the release zip")
    args = parser.parse_args()

    with open(args.manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    plugin = next((p for p in manifest if p["guid"] == args.guid), None)
    if plugin is None:
        print(f"No plugin with guid {args.guid} found in {args.manifest_path}", file=sys.stderr)
        return 1

    plugin["versions"] = [v for v in plugin["versions"] if v["version"] != args.version]
    plugin["versions"].insert(0, {
        "version": args.version,
        "changelog": args.changelog,
        "targetAbi": args.target_abi,
        "sourceUrl": args.source_url,
        "checksum": args.checksum,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    with open(args.manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print(f"Added version {args.version} to {args.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
