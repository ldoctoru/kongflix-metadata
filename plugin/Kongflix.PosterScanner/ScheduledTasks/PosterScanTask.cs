using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Kongflix.PosterScanner.Configuration;
using Kongflix.PosterScanner.Scanning;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.IO;
using MediaBrowser.Model.Tasks;
using Microsoft.Extensions.Logging;

namespace Kongflix.PosterScanner.ScheduledTasks;

/// <summary>
/// Scheduled (and manually triggerable) task that scans for items missing a
/// poster and forces Jellyfin's configured agents to refresh them.
/// </summary>
public class PosterScanTask : IScheduledTask
{
    private readonly PosterLibraryScanner _scanner;
    private readonly IProviderManager _providerManager;
    private readonly IFileSystem _fileSystem;
    private readonly ILogger<PosterScanTask> _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="PosterScanTask"/> class.
    /// </summary>
    /// <param name="libraryManager">Library manager.</param>
    /// <param name="providerManager">Provider manager.</param>
    /// <param name="fileSystem">File system.</param>
    /// <param name="logger">Logger.</param>
    public PosterScanTask(
        ILibraryManager libraryManager,
        IProviderManager providerManager,
        IFileSystem fileSystem,
        ILogger<PosterScanTask> logger)
    {
        _scanner = new PosterLibraryScanner(libraryManager);
        _providerManager = providerManager;
        _fileSystem = fileSystem;
        _logger = logger;
    }

    /// <inheritdoc />
    public string Name => "Scan for Missing Posters";

    /// <inheritdoc />
    public string Key => "KongflixPosterScan";

    /// <inheritdoc />
    public string Description =>
        "Scans movie and series libraries for items missing a poster and forces a metadata refresh for them.";

    /// <inheritdoc />
    public string Category => "Library";

    /// <inheritdoc />
    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers()
    {
        yield return new TaskTriggerInfo
        {
            Type = TaskTriggerInfo.TriggerDaily,
            TimeOfDayTicks = TimeSpan.FromHours(3).Ticks,
        };
    }

    /// <inheritdoc />
    public Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken)
    {
        return RunScanAsync(Plugin.Instance!.Configuration, progress, cancellationToken);
    }

    /// <summary>
    /// Runs the scan-and-refresh logic against an explicit configuration,
    /// independent of the live <see cref="Plugin.Instance"/> singleton so it
    /// can be unit tested directly.
    /// </summary>
    /// <param name="config">The configuration to run with.</param>
    /// <param name="progress">Progress reporter.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    internal async Task RunScanAsync(PluginConfiguration config, IProgress<double> progress, CancellationToken cancellationToken)
    {
        var missing = _scanner.FindItemsMissingPosters(config);

        _logger.LogInformation("Poster scan found {Count} item(s) missing a poster", missing.Count);

        if (config.DryRun)
        {
            foreach (var item in missing)
            {
                _logger.LogInformation("[Dry run] Would refresh: {Name} ({Id})", item.Name, item.Id);
            }

            progress.Report(100);
            return;
        }

        var toRefresh = config.MaxItemsPerScan > 0
            ? missing.Take(config.MaxItemsPerScan).ToList()
            : missing;

        if (toRefresh.Count < missing.Count)
        {
            _logger.LogInformation(
                "Refreshing {ToRefresh} of {Total} item(s) this run; the rest will be picked up next scan",
                toRefresh.Count,
                missing.Count);
        }

        var refreshOptions = new MetadataRefreshOptions(new DirectoryService(_fileSystem))
        {
            MetadataRefreshMode = MetadataRefreshMode.FullRefresh,
            ImageRefreshMode = MetadataRefreshMode.FullRefresh,
            ReplaceAllMetadata = true,
            ReplaceAllImages = true,
            ForceSave = true,
        };

        for (var i = 0; i < toRefresh.Count; i++)
        {
            var item = toRefresh[i];

            try
            {
                await _providerManager.RefreshSingleItem(item, refreshOptions, cancellationToken)
                    .ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to refresh {Name} ({Id})", item.Name, item.Id);
            }

            progress.Report((i + 1) * 100.0 / toRefresh.Count);
        }
    }
}
