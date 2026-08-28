using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Kongflix.PosterScanner.Configuration;
using Kongflix.PosterScanner.ScheduledTasks;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.IO;
using Microsoft.Extensions.Logging;
using Moq;
using Xunit;

namespace Kongflix.PosterScanner.Tests;

public class PosterScanTaskTests
{
    private static (PosterScanTask Task, Mock<ILibraryManager> LibraryManager, Mock<IProviderManager> ProviderManager) CreateTask()
    {
        var libraryId = Guid.NewGuid();
        var libraryManager = new Mock<ILibraryManager>();
        libraryManager.Setup(m => m.GetVirtualFolders()).Returns(new List<VirtualFolderInfo>
        {
            new() { ItemId = libraryId.ToString(), Name = "Movies", CollectionType = CollectionTypeOptions.movies },
        });

        var missing = Enumerable.Range(0, 3)
            .Select(i => (BaseItem)new Movie { Name = $"Movie {i}", ImageInfos = Array.Empty<ItemImageInfo>() })
            .ToList();

        libraryManager.Setup(m => m.GetItemList(It.IsAny<InternalItemsQuery>())).Returns(missing);

        var providerManager = new Mock<IProviderManager>();
        providerManager
            .Setup(m => m.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(ItemUpdateType.MetadataDownload);

        var fileSystem = new Mock<IFileSystem>();
        var logger = new Mock<ILogger<PosterScanTask>>();

        var task = new PosterScanTask(libraryManager.Object, providerManager.Object, fileSystem.Object, logger.Object);

        return (task, libraryManager, providerManager);
    }

    [Fact]
    public async Task RefreshesEveryFlaggedItemWhenUnderTheCap()
    {
        var (task, _, providerManager) = CreateTask();
        var config = new PluginConfiguration { MaxItemsPerScan = 0, DryRun = false };

        await task.RunScanAsync(config, new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            m => m.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Exactly(3));
    }

    [Fact]
    public async Task RespectsMaxItemsPerScan()
    {
        var (task, _, providerManager) = CreateTask();
        var config = new PluginConfiguration { MaxItemsPerScan = 2, DryRun = false };

        await task.RunScanAsync(config, new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            m => m.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Exactly(2));
    }

    [Fact]
    public async Task DryRunNeverTriggersARefresh()
    {
        var (task, _, providerManager) = CreateTask();
        var config = new PluginConfiguration { DryRun = true };

        await task.RunScanAsync(config, new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            m => m.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task ForcesAFullMetadataAndImageRefresh()
    {
        var (task, _, providerManager) = CreateTask();
        var config = new PluginConfiguration { MaxItemsPerScan = 1, DryRun = false };

        await task.RunScanAsync(config, new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            m => m.RefreshSingleItem(
                It.IsAny<BaseItem>(),
                It.Is<MetadataRefreshOptions>(o =>
                    o.MetadataRefreshMode == MetadataRefreshMode.FullRefresh &&
                    o.ImageRefreshMode == MetadataRefreshMode.FullRefresh &&
                    o.ReplaceAllMetadata &&
                    o.ReplaceAllImages &&
                    o.ForceSave),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task OneFailingRefreshDoesNotStopTheRest()
    {
        var (task, _, providerManager) = CreateTask();
        providerManager
            .SetupSequence(m => m.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("boom"))
            .ReturnsAsync(ItemUpdateType.MetadataDownload)
            .ReturnsAsync(ItemUpdateType.MetadataDownload);

        var config = new PluginConfiguration { MaxItemsPerScan = 0, DryRun = false };

        await task.RunScanAsync(config, new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            m => m.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Exactly(3));
    }
}
