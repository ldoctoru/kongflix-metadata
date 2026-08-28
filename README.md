# Kongflix Metadata Scanner

A native Jellyfin plugin (C#/.NET) that scans your library for items
missing a poster or overview and triggers Jellyfin's own metadata
refresh for them.

See [`plugin/README.md`](plugin/README.md) for build, install, and
usage instructions.

> **Status: builds and unit tests pass** (11/11) against the real
> Jellyfin Plugin SDK. Not yet verified: loading and running inside an
> actual Jellyfin server (install steps in `plugin/README.md`).

## Archive

This repository previously shipped a separate Docker/Python tool with
the same goal, run as a standalone container talking to Jellyfin's
REST API. That implementation is preserved for reference under
[`archive/`](archive/) — it is no longer maintained; the plugin in
`plugin/` is its replacement.
