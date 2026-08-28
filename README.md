# Kongflix Poster Scanner

A native Jellyfin plugin (C#/.NET) that scans movie and series libraries
for items missing a poster and forces Jellyfin's own agents to refresh
them.

See [`plugin/README.md`](plugin/README.md) for what it does, its
settings, and build/install instructions.

> **Status: builds and unit tests pass** (12/12) against the real
> Jellyfin Plugin SDK. Not yet verified: loading and running inside an
> actual Jellyfin server.
