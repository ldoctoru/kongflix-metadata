# Kongflix Metadata Scanner

A native Jellyfin plugin (C#/.NET) that scans your library for items
missing a poster or overview and triggers Jellyfin's own metadata
refresh for them.

See [`plugin/README.md`](plugin/README.md) for build, install, and
usage instructions.

> **Status: builds and unit tests pass** (11/11) against the real
> Jellyfin Plugin SDK. Not yet verified: loading and running inside an
> actual Jellyfin server (install steps in `plugin/README.md`).

## Install in Jellyfin

Dashboard → Plugins → Repositories → Add Repository:

| Field | Value |
|---|---|
| Repository Name | `Kongflix` (or anything you like) |
| Repository URL | `https://raw.githubusercontent.com/ldoctoru/kongflix-metadata/main/manifest.json` |

Then Dashboard → Plugins → Catalog → "Kongflix Metadata Scanner" →
Install. (The Catalog only lists a version once one has been published
— see [`plugin/README.md`](plugin/README.md#releasing-a-new-version).)

## Archive

This repository previously shipped a separate Docker/Python tool with
the same goal, run as a standalone container talking to Jellyfin's
REST API. That implementation is preserved for reference under
[`archive/`](archive/) — it is no longer maintained; the plugin in
`plugin/` is its replacement.
