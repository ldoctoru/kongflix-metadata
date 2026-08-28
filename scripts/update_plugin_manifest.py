#!/usr/bin/env python3
"""Add or replace a version entry in manifest.json for the Jellyfin plugin repository.

Usage:
    update_plugin_manifest.py \
        --manifest manifest.json \
        --guid 5f3b2c1a-8e4d-4a6b-9c2f-1a2b3c4d5e6f \
        --version 1.0.0.0 \
        --checksum <md5-hex> \
        --source-url https://.../kongflix-metadata-scanner_1.0.0.0.zip \
        --target-abi 10.9.0.0 \
        --changelog "Initial MVP release." \
        --timestamp 2026-08-28T00:00:00Z
"""
import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--guid", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--checksum", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--target-abi", required=True)
    parser.add_argument("--changelog", default="")
    parser.add_argument("--timestamp", required=True)
    args = parser.parse_args()

    with open(args.manifest, "r") as f:
        entries = json.load(f)

    plugin_entry = None
    for entry in entries:
        if entry.get("guid") == args.guid:
            plugin_entry = entry
            break

    if plugin_entry is None:
        print(f"error: no manifest entry with guid {args.guid!r} found in {args.manifest}", file=sys.stderr)
        return 1

    new_version = {
        "version": args.version,
        "changelog": args.changelog,
        "targetAbi": args.target_abi,
        "sourceUrl": args.source_url,
        "checksum": args.checksum,
        "timestamp": args.timestamp,
    }

    versions = plugin_entry.setdefault("versions", [])
    versions[:] = [v for v in versions if v.get("version") != args.version]
    versions.insert(0, new_version)

    with open(args.manifest, "w") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")

    print(f"Added version {args.version} to {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
