using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Kongflix.MetadataScanner.Configuration;
using Kongflix.MetadataScanner.Scanning;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.IO;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Tasks;
using Microsoft.Extensions.Logging;

namespace Kongflix.MetadataScanner.ScheduledTasks;

public class MetadataScanTask : IScheduledTask
{
    private readonly ILibraryManager _libraryManager;
    private readonly IProviderManager _providerManager;
    private readonly IDirectoryService _directoryService;
    private readonly ILogger<MetadataScanTask> _logger;
    private readonly PluginConfiguration _config;

    public MetadataScanTask(
        ILibraryManager libraryManager,
        IProviderManager providerManager,
        IDirectoryService directoryService,
        ILogger<MetadataScanTask> logger,
        PluginConfiguration? config = null)
    {
        _libraryManager = libraryManager;
        _providerManager = providerManager;
        _directoryService = directoryService;
        _logger = logger;
        _config = config ?? Plugin.Instance!.Configuration;
    }

    public string Name => "Scan for Missing Metadata";

    public string Key => "KongflixMetadataScan";

    public string Description => "Scans the library for items missing a poster or overview and triggers a metadata refresh for them.";

    public string Category => "Library";

    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers()
    {
        yield return new TaskTriggerInfo
        {
            Type = TaskTriggerInfo.TriggerDaily,
            TimeOfDayTicks = TimeSpan.FromHours(3).Ticks,
        };
    }

    public async Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken)
    {
        var excludeTypes = (_config.ExcludeItemTypes ?? string.Empty)
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .ToList();

        var query = new InternalItemsQuery
        {
            Recursive = true,
        };
        if (excludeTypes.Count > 0)
        {
            // NOTE: InternalItemsQuery's exact property for excluding by type
            // name may differ (e.g. ExcludeItemTypes taking BaseItemKind[]
            // rather than string[]) — adjust to match the real SDK type here
            // once building against the actually-restored package version.
            query.ExcludeItemTypes = excludeTypes.ToArray();
        }

        var items = _libraryManager.GetItemList(query);
        var flaggedItems = items.Where(MissingMetadataChecker.IsMissingMetadata).ToList();

        var itemsToRefresh = flaggedItems.Take(_config.MaxRefreshesPerRun).ToList();

        var refreshed = 0;
        var failed = 0;
        var processed = 0;

        foreach (var item in itemsToRefresh)
        {
            cancellationToken.ThrowIfCancellationRequested();

            try
            {
                var options = new MetadataRefreshOptions(_directoryService)
                {
                    MetadataRefreshMode = MediaBrowser.Controller.Providers.MetadataRefreshMode.FullRefresh,
                    ImageRefreshMode = MediaBrowser.Controller.Providers.MetadataRefreshMode.FullRefresh,
                    ReplaceAllMetadata = false,
                    ReplaceAllImages = false,
                };
                await _providerManager.RefreshSingleItem(item, options, cancellationToken).ConfigureAwait(false);
                refreshed++;
            }
            catch (Exception error)
            {
                failed++;
                _logger.LogError(error, "Failed to refresh item {ItemName}", item.Name);
            }

            processed++;
            progress.Report(100.0 * processed / Math.Max(1, itemsToRefresh.Count));
        }

        var skipped = flaggedItems.Count - itemsToRefresh.Count;
        _logger.LogInformation(
            "Kongflix metadata scan complete: scanned={Scanned} flagged={Flagged} refreshed={Refreshed} failed={Failed} skipped={Skipped}",
            items.Count,
            flaggedItems.Count,
            refreshed,
            failed,
            skipped);
    }
}
