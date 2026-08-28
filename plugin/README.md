# Kongflix Poster Scanner (Jellyfin Plugin)

A native Jellyfin plugin that scans your movie and TV libraries for items
missing a poster and forces Jellyfin's configured metadata agents to
refresh them.

## What it does

- Scans every included library for **movies** and **series** — the series
  entry itself, never its seasons or episodes (a "second level" is never
  checked).
- An item is flagged if it has no **primary image** (poster).
- Music, home video, box set and book libraries are excluded by default —
  they have no comparable poster concept — but every library can be
  individually included or excluded from the plugin's settings page.
- Flagged items get a forced **full metadata + image refresh**
  (`MetadataRefreshMode.FullRefresh` + `ImageRefreshMode.FullRefresh`,
  replacing existing metadata/images) via Jellyfin's own `IProviderManager`
  — Jellyfin's configured providers (TMDb, TVDB, etc.) do the actual
  lookup. A per-item failure is logged and does not stop the rest of the
  scan.
- Runs on a daily schedule by default, or on demand — see
  [Running a scan](#running-a-scan) below.

## Settings page

Dashboard → Plugins → Kongflix Poster Scanner exposes:

- **Libraries to scan** — a checkbox per server library.
- **Max items refreshed per scan** — caps how many flagged items get
  refreshed in one run so a large backlog doesn't hammer your metadata
  providers; the rest are picked up on the next run. `0` = no limit.
- **Dry run** — log what would be refreshed without actually refreshing
  anything.
- **Run scan now** — triggers an immediate scan without waiting for the
  schedule.

## Running a scan

- **Manually**: click **Run scan now** on the settings page, or go to
  Dashboard → Scheduled Tasks → "Scan for Missing Posters" → run.
- **Scheduled**: the task runs daily at 3 AM by default; change the
  trigger from Dashboard → Scheduled Tasks like any other Jellyfin task.

## Building

Requires the .NET 9 SDK (matching Jellyfin's own runtime as of 10.11.x).

```bash
cd plugin
dotnet restore
dotnet build --configuration Release
dotnet test Kongflix.PosterScanner.Tests/Kongflix.PosterScanner.Tests.csproj
```

## Installing via the plugin repository (recommended)

This repository publishes a Jellyfin plugin repository manifest at
[`manifest.json`](../manifest.json), kept up to date by the "Build and
release plugin" GitHub Actions workflow (see
[Releasing a new version](#releasing-a-new-version) below).

1. In Jellyfin, go to **Dashboard → Plugins → Repositories → Add
   Repository**.
2. Fill in:

   | Field | Value |
   |---|---|
   | Repository Name | `Kongflix` (or anything you like) |
   | Repository URL | `https://raw.githubusercontent.com/ldoctoru/kongflix-metadata/main/manifest.json` |

3. Go to **Dashboard → Plugins → Catalog**, find "Kongflix Poster
   Scanner," and install it.
4. Restart Jellyfin when prompted.
5. Continue from step 4 in [Installing (manual, local build)](#installing-manual-local-build)
   below.

> **Note:** the catalog only shows a version once one has actually been
> published — see [Releasing a new version](#releasing-a-new-version)
> below. Adding the repository before any version exists is harmless;
> the plugin just won't appear in the Catalog list yet.

## Installing (manual, local build)

1. Build the project in Release mode (see [Building](#building) above).
2. Copy the built output
   (`Kongflix.PosterScanner/bin/Release/net9.0/Kongflix.PosterScanner.dll`
   and any dependent DLLs not already present in Jellyfin's own `System`
   folder) into a new folder under Jellyfin's plugin directory, e.g.
   `<jellyfin-data>/plugins/Kongflix Poster Scanner/`.
3. Restart Jellyfin.
4. In Dashboard → Plugins, confirm "Kongflix Poster Scanner" is listed
   and enabled, then configure it from its settings page.

## Releasing a new version

The "Build and release plugin" workflow
(`.github/workflows/build-plugin.yml`) builds the plugin in Release
mode, runs the test suite, zips the output, creates a GitHub Release
with that zip attached, and updates [`manifest.json`](../manifest.json)
with the new version's download URL and MD5 checksum — all in one run.

To trigger it: on GitHub, go to **Actions → Build and release plugin →
Run workflow**, and fill in:

- **version** — e.g. `1.0.0.0` (must be a valid 4-part .NET assembly
  version)
- **target_abi** — the minimum Jellyfin server version this build
  supports (default `10.11.0.0`)
- **changelog** — a short description of what changed

Once it finishes, anyone with this repository already added in
Jellyfin will see the new version available under Dashboard → Plugins
→ Catalog (or an update prompt if already installed).

## Status

Builds and all unit tests pass against the real Jellyfin Plugin SDK
(`Jellyfin.Controller` 10.11.11, target ABI 10.11.0.0), and has been
confirmed running against a live Jellyfin 10.11.11 server.

### Version compatibility

Jellyfin's plugin API isn't binary-stable across releases: several
`ILibraryManager`/`TaskTriggerInfo` signatures changed between 10.10.x
and 10.11.x (which also moved Jellyfin's own runtime from .NET 8 to
.NET 9), causing a `MissingMethodException` at scan time when a build
compiled against an older SDK version is loaded into a newer server.
v1.0.0.0 was built against 10.9.11 and only works on servers up to
~10.10.x; v1.0.1.0 onward targets 10.11.11/.NET 9 and requires a
10.11.x+ server. If you're on an older Jellyfin server, use v1.0.0.0
instead, or open an issue.
