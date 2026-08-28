# Kongflix Metadata Scanner (Jellyfin Plugin)

A native Jellyfin plugin that scans your library for items missing a
poster or overview and triggers Jellyfin's own metadata refresh for
them — the in-process successor to the standalone Docker-based
kongflix-metadata tool.

> **Status: unverified.** This code was authored in an environment with
> no .NET SDK installed, so nothing here has actually been compiled or
> run yet. Some of Jellyfin's Plugin SDK API surface (exact method and
> property names) may differ slightly from what's used here depending
> on the exact NuGet package version that resolves — expect to fix a
> few compile errors on the first build. See the inline `NOTE:` comment
> in `ScheduledTasks/MetadataScanTask.cs` for the most likely spot.

## Building

Requires the .NET 8 SDK.

```bash
cd plugin
dotnet restore
dotnet build --configuration Release
dotnet test
```

## Installing (manual, local build)

1. Build the project in Release mode (see above).
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

MVP: scan + refresh + basic config. Not yet built: a missing-items
list/history view, per-item manual retry, and a real-time
newly-added-item watcher (planned as follow-up work, matching the
Docker app's feature set incrementally).
