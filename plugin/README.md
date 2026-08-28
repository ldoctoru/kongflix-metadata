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

Requires the .NET 8 SDK.

```bash
cd plugin
dotnet restore
dotnet build --configuration Release
dotnet test Kongflix.PosterScanner.Tests/Kongflix.PosterScanner.Tests.csproj
```

## Installing (manual, local build)

1. Build the project in Release mode (see [Building](#building) above).
2. Copy the built output
   (`Kongflix.PosterScanner/bin/Release/net8.0/Kongflix.PosterScanner.dll`
   and any dependent DLLs not already present in Jellyfin's own `System`
   folder) into a new folder under Jellyfin's plugin directory, e.g.
   `<jellyfin-data>/plugins/Kongflix Poster Scanner/`.
3. Restart Jellyfin.
4. In Dashboard → Plugins, confirm "Kongflix Poster Scanner" is listed
   and enabled, then configure it from its settings page.

## Status

Builds and all unit tests pass against the real Jellyfin Plugin SDK
(`Jellyfin.Controller` 10.9.11, target ABI 10.9.0.0). Not yet verified:
loading and running inside an actual live Jellyfin server.
