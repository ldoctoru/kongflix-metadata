# Jellyfin Plugin MVP — Design

## Purpose

Replace the Docker/Python "kongflix-metadata" tool with a native Jellyfin
plugin that runs inside Jellyfin's own server process. This is the MVP
(first sub-project): a Scheduled Task that scans the library for items
missing a poster or overview and triggers Jellyfin's own metadata
refresh for them, plus a minimal admin config page. Follow-up plans add
the missing-items list/history UI, per-item retry, and a watch-mode
equivalent — matching the Docker app's feature set incrementally, the
same way that app itself was built.

Running in-process (rather than as a separate container talking to
Jellyfin's REST API) removes an entire class of problems the Docker app
had to work around: no API key, no HTTP round-trips, no separate web
server/port, no custom cron parser (Jellyfin's own Scheduled Tasks
engine handles scheduling), and — critically — `RefreshSingleItem` can
be genuinely awaited, so the plugin knows whether a refresh actually
succeeded instead of just whether Jellyfin *accepted* the request (the
root cause of the "same items every scan" issue investigated in the
Docker app).

## Approach

A standard Jellyfin plugin project targeting the current Plugin
SDK/.NET 8 (matching Jellyfin 10.9.x/10.10.x's ABI), placed at `/plugin`
in this repository, alongside the existing Python app (which stays in
place until this plugin reaches feature parity).

## Components

- `plugin/Kongflix.MetadataScanner.csproj` — targets `net8.0`; references
  the `Jellyfin.Controller` and `Jellyfin.Model` NuGet packages (the
  current community-plugin-standard packages exposing
  `ILibraryManager`, `IProviderManager`, `BasePlugin<T>`,
  `IScheduledTask`, etc.).

- `Plugin.cs`
  - `public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages`
  - Standard Jellyfin plugin entry point: exposes `Id` (a fixed GUID),
    `Name`, `Description`, and `GetPages()` returning the single config
    page's `PluginPageInfo`.

- `Configuration/PluginConfiguration.cs`
  - `public class PluginConfiguration : BasePluginConfiguration`
  - `public string ExcludeItemTypes { get; set; } = "Season,BoxSet,CollectionFolder,Audio,MusicAlbum,MusicArtist";`
  - `public int MaxRefreshesPerRun { get; set; } = 200;`
  - Persisted automatically by Jellyfin's plugin configuration
    machinery (XML-serialized to Jellyfin's plugin config directory) —
    no custom load/save code needed.

- `Configuration/configPage.html`
  - A minimal HTML page using Jellyfin's dashboard plugin-config
    conventions (the same pattern every community plugin's config page
    uses): a text input for `ExcludeItemTypes`, a number input for
    `MaxRefreshesPerRun`, a Save button wired to Jellyfin's
    `ApiClient.updatePluginConfiguration` JS helper. Registered as an
    embedded resource and returned via `Plugin.GetPages()`.

- `Scanning/MissingMetadataChecker.cs`
  - `public static bool IsMissingMetadata(BaseItem item)` — pure,
    testable predicate: `!item.HasImage(ImageType.Primary) || string.IsNullOrWhiteSpace(item.Overview)`.
    Mirrors the Docker app's `is_missing_metadata` exactly, translated
    to Jellyfin's in-process item model.

- `ScheduledTasks/MetadataScanTask.cs`
  - `public class MetadataScanTask : IScheduledTask`
  - `Execute(IProgress<double> progress, CancellationToken cancellationToken)`:
    1. Reads `ExcludeItemTypes`/`MaxRefreshesPerRun` from
       `Plugin.Instance.Configuration`.
    2. Enumerates items via `ILibraryManager.GetItemList(query)`,
       passing an `InternalItemsQuery` with `ExcludeItemTypes` set from
       the parsed config (Jellyfin's query API supports this natively —
       same idea as the Docker app's plan to use Jellyfin's
       `ExcludeItemTypes` REST parameter, just via the in-process query
       object instead).
    3. Filters the result through `MissingMetadataChecker.IsMissingMetadata`.
    4. For up to `MaxRefreshesPerRun` flagged items, calls
       `await _providerManager.RefreshSingleItem(item, new MetadataRefreshOptions(_directoryService) { MetadataRefreshMode = MetadataRefreshMode.FullRefresh, ImageRefreshMode = MetadataRefreshMode.FullRefresh }, cancellationToken)`,
       wrapped in a `try/catch` per item so one failure doesn't abort
       the loop (same per-item isolation principle as the Docker app).
    5. Reports progress via the `progress` callback as a percentage of
       items processed.
    6. Logs a final summary line (scanned/flagged/refreshed/failed
       counts) via injected `ILogger<MetadataScanTask>` — visible in
       Jellyfin's own log viewer and the Scheduled Task's execution
       history, which already shows start/end time and success/failure
       per run without any custom code.
  - `GetDefaultTriggers()` returns a single daily trigger (e.g. 3 AM),
    matching the Docker app's `0 3 * * *` default — the *user* can then
    change this from Jellyfin's own Scheduled Tasks page, exactly like
    any other built-in task (e.g. "Scan Media Library").
  - Constructor takes `ILibraryManager`, `IProviderManager`,
    `IDirectoryService`, `ILogger<MetadataScanTask>` via Jellyfin's
    dependency injection (registered automatically since the class
    implements `IScheduledTask` and Jellyfin discovers it via
    reflection on plugin load — no manual DI registration file needed
    for this specific interface).

- `manifest.json` (plugin repository descriptor, for later distribution
  via a custom Jellyfin plugin repository URL) — deferred until the
  plugin is installable/testable; not required for local development
  (a plugin can be built and dropped into Jellyfin's `plugins/` folder
  directly for testing without a repository manifest).

## Data flow

Jellyfin's Scheduled Tasks engine (its own UI: Dashboard → Scheduled
Tasks → shows this task listed alongside built-ins like "Scan Media
Library") triggers `MetadataScanTask.Execute` on the configured
interval → enumerate non-excluded items → filter for missing
poster/overview → for each (up to the cap), await
`RefreshSingleItem` → catch and log any per-item failure → log final
summary → task completes; Jellyfin's own task-history UI shows the
run's start/end time and success/failure state automatically.

## Error handling

- **Per-item**: a failed `RefreshSingleItem` call (thrown exception, or
  an unsuccessful outcome) is caught immediately around that single
  call, logged with the item's name and error, and the loop continues
  to the next item — mirrors the Docker app's `run_once` isolation.
- **Task-level**: any unhandled exception outside the per-item try/catch
  (e.g. `ILibraryManager.GetItemList` itself throwing) propagates up
  and is caught by Jellyfin's own Scheduled Task runner, which already
  marks the task run as failed in its history UI and logs the
  exception — no custom top-level error handling needed, since this is
  exactly what Jellyfin already does for every built-in task.

## Testing

- `plugin/Kongflix.MetadataScanner.Tests/` — xUnit test project.
  - `MissingMetadataCheckerTests`: `IsMissingMetadata` returns
    `true`/`false` for the same edge cases the Docker app's
    `describe_missing_reasons`/`is_missing_metadata` tests cover
    (missing poster only, missing overview only, both, neither),
    constructed via real (lightweight, in-memory) `BaseItem` subclass
    instances rather than mocks, since `HasImage`/`Overview` are plain
    properties.
  - `MetadataScanTaskTests`: using Moq for `ILibraryManager`/
    `IProviderManager`, verify: (a) items of an excluded type are never
    passed to `RefreshSingleItem`, (b) a `RefreshSingleItem` exception
    on one item doesn't stop processing of subsequent items, (c) the
    loop stops calling `RefreshSingleItem` once `MaxRefreshesPerRun` is
    reached, even if more flagged items remain.
  - `PluginConfigurationTests`: default values match the documented
    defaults; `ExcludeItemTypes`'s comma-separated string round-trips
    correctly when parsed into a list (whitespace trimmed, empty
    entries dropped, matching the Docker app's parsing behavior for
    consistency even though this is a separate implementation).

## Out of scope (MVP — deferred to follow-up plans)

- Missing-items list / scan-history UI (the Docker app's dashboard
  equivalent).
- Per-item manual retry, "Clear List".
- A `watch`-mode equivalent (a follow-up would hook
  `ILibraryManager.ItemAdded` directly — even more natural in-process
  than the Docker app's websocket-based approach, since no separate
  connection is needed at all).
- Plugin repository `manifest.json`/distribution — local build-and-drop
  install only for MVP.
- Retiring the Python/Docker app — happens once this plugin reaches
  feature parity, not as part of MVP.
