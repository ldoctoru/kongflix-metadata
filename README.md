# Kongflix Metadata Scanner

A native Jellyfin plugin (C#/.NET) that scans your library for items
missing a poster or overview and triggers Jellyfin's own metadata
refresh for them.

See [`plugin/README.md`](plugin/README.md) for build, install, and
usage instructions.

> **Status: unverified.** This code was authored without access to a
> .NET SDK, so it has not yet been compiled or run against a real
> Jellyfin server. See `plugin/README.md` for the exact build/test
> commands and known likely trouble spots before relying on it.

## Archive

This repository previously shipped a separate Docker/Python tool with
the same goal, run as a standalone container talking to Jellyfin's
REST API. That implementation is preserved for reference under
[`archive/`](archive/) — it is no longer maintained, and the plugin in
`plugin/` is its intended replacement once verified.
