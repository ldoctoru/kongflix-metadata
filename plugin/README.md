# Kongflix Metadata Scanner (Jellyfin Plugin)

A native Jellyfin plugin that scans your library for items missing a
poster or overview and triggers Jellyfin's own metadata refresh for
them — the in-process successor to the standalone Docker-based
kongflix-metadata tool.

> **Status: builds and all 11 unit tests pass** against the real
> Jellyfin Plugin SDK. Not yet verified: loading and running inside an
> actual Jellyfin server.

## Building

Requires the .NET 8 SDK (or a newer SDK, e.g. .NET 10, with the .NET 8
runtime also installed side-by-side — the plugin targets `net8.0` to
match Jellyfin's own runtime, and running the test suite needs that
runtime present even if your SDK is newer).

```bash
cd plugin
dotnet restore
dotnet build --configuration Release
dotnet test Kongflix.MetadataScanner.Tests/Kongflix.MetadataScanner.Tests.csproj
```

Note: running plain `dotnet test` from this directory picks up the
main library project (not a test project) and reports nothing to run —
point it at the test `.csproj` explicitly, as shown above.

## Installing via the plugin repository (recommended)

This repository publishes a Jellyfin plugin repository manifest at
[`manifest.json`](../manifest.json), kept up to date automatically by
the "Build and release plugin" GitHub Actions workflow (see
[Releasing a new version](#releasing-a-new-version) below).

1. In Jellyfin, go to **Dashboard → Plugins → Repositories → Add
   Repository**.
2. Set **Repository Name** to anything (e.g. "Kongflix") and
   **Repository URL** to:
   ```
   https://raw.githubusercontent.com/ldoctoru/kongflix-metadata/main/manifest.json
   ```
3. Go to **Dashboard → Plugins → Catalog**, find "Kongflix Metadata
   Scanner," and install it.
4. Restart Jellyfin when prompted.
5. Continue from step 4 below.

## Installing (manual, local build)

1. Build the project in Release mode (see [Building](#building) above).
2. Copy the built output (`bin/Release/net8.0/Kongflix.MetadataScanner.dll`
   and any dependent DLLs not already present in Jellyfin's own
   `System` folder) into a new folder under Jellyfin's plugin
   directory, e.g. `<jellyfin-data>/plugins/Kongflix Metadata Scanner/`.
3. Restart Jellyfin.
4. In Jellyfin's Dashboard → Plugins, confirm "Kongflix Metadata
   Scanner" is listed and enabled.
5. In Dashboard → Scheduled Tasks, find "Scan for Missing Metadata"
   under the Library category — you can run it on demand or adjust its
   trigger (default: daily at 3 AM).
6. In Dashboard → Plugins → Kongflix Metadata Scanner, configure
   `Exclude Item Types` and `Max Refreshes Per Run` as needed.

## Releasing a new version

The "Build and release plugin" workflow (`.github/workflows/build-plugin.yml`)
builds the plugin in Release mode, runs the test suite, zips the
output, creates a GitHub Release with that zip attached, and updates
[`manifest.json`](../manifest.json) with the new version's download
URL and MD5 checksum — all in one run.

To trigger it: on GitHub, go to **Actions → Build and release plugin →
Run workflow**, and fill in:

- **version** — e.g. `1.0.1.0` (must be a valid 4-part .NET assembly
  version)
- **target_abi** — the minimum Jellyfin server version this build
  supports (default `10.9.0.0`)
- **changelog** — a short description of what changed

Once it finishes, anyone with this repository already added in
Jellyfin will see the new version available under Dashboard → Plugins
→ Catalog (or an update prompt if already installed).

## What it does

Scans all library items except the configured excluded types (default:
`Season, BoxSet, CollectionFolder, Audio, MusicAlbum, MusicArtist`).
An item is flagged if it has no poster image or no overview/plot text.
Flagged items (up to `Max Refreshes Per Run` per scan) get a full
metadata refresh requested via Jellyfin's own `IProviderManager` —
Jellyfin's configured providers (TMDb, TVDB, etc.) do the actual
lookup. A per-item failure is logged and does not stop the rest of the
scan.

## Status

MVP: scan + refresh + basic config — builds and all unit tests pass.
Not yet verified in a real Jellyfin server, and not yet built: a
missing-items list/history view, per-item manual retry, and a
real-time newly-added-item watcher (planned as follow-up work,
matching the archived Docker app's feature set incrementally).
