using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Kongflix.MetadataScanner.Configuration;
using Kongflix.MetadataScanner.ScheduledTasks;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.IO;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Providers;
using Microsoft.Extensions.Logging;
using Moq;
using Xunit;

namespace Kongflix.MetadataScanner.Tests;

public class MetadataScanTaskTests
{
    private static Movie MakeFlaggedItem(string id)
    {
        return new Movie
        {
            Id = Guid.NewGuid(),
            Name = id,
            Overview = null,
        };
    }

    [Fact]
    public async Task Execute_RefreshesOnlyFlaggedItems()
    {
        var complete = new Movie { Id = Guid.NewGuid(), Name = "Complete", Overview = "ok" };
        complete.ImageInfos = new[] { new MediaBrowser.Model.Entities.ItemImageInfo { Path = "/x.jpg", Type = MediaBrowser.Model.Entities.ImageType.Primary } };
        var missing1 = MakeFlaggedItem("Missing1");
        var missing2 = MakeFlaggedItem("Missing2");

        var libraryManager = new Mock<ILibraryManager>();
        libraryManager
            .Setup(lm => lm.GetItemList(It.IsAny<InternalItemsQuery>()))
            .Returns(new List<BaseItem> { complete, missing1, missing2 });

        var providerManager = new Mock<IProviderManager>();
        providerManager
            .Setup(pm => pm.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        var directoryService = new Mock<IDirectoryService>();
        var logger = new Mock<ILogger<MetadataScanTask>>();

        var config = new PluginConfiguration { MaxRefreshesPerRun = 200 };

        var task = new MetadataScanTask(libraryManager.Object, providerManager.Object, directoryService.Object, logger.Object, config);

        await task.Execute(new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            pm => pm.RefreshSingleItem(missing1, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Once);
        providerManager.Verify(
            pm => pm.RefreshSingleItem(missing2, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Once);
        providerManager.Verify(
            pm => pm.RefreshSingleItem(complete, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task Execute_IsolatesPerItemFailures()
    {
        var bad = MakeFlaggedItem("Bad");
        var good = MakeFlaggedItem("Good");

        var libraryManager = new Mock<ILibraryManager>();
        libraryManager
            .Setup(lm => lm.GetItemList(It.IsAny<InternalItemsQuery>()))
            .Returns(new List<BaseItem> { bad, good });

        var providerManager = new Mock<IProviderManager>();
        providerManager
            .Setup(pm => pm.RefreshSingleItem(bad, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("boom"));
        providerManager
            .Setup(pm => pm.RefreshSingleItem(good, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        var directoryService = new Mock<IDirectoryService>();
        var logger = new Mock<ILogger<MetadataScanTask>>();
        var config = new PluginConfiguration { MaxRefreshesPerRun = 200 };

        var task = new MetadataScanTask(libraryManager.Object, providerManager.Object, directoryService.Object, logger.Object, config);

        // Must not throw, despite "bad" failing.
        await task.Execute(new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            pm => pm.RefreshSingleItem(good, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task Execute_StopsAtMaxRefreshesPerRun()
    {
        var items = new List<BaseItem>
        {
            MakeFlaggedItem("1"),
            MakeFlaggedItem("2"),
            MakeFlaggedItem("3"),
        };

        var libraryManager = new Mock<ILibraryManager>();
        libraryManager
            .Setup(lm => lm.GetItemList(It.IsAny<InternalItemsQuery>()))
            .Returns(items);

        var providerManager = new Mock<IProviderManager>();
        providerManager
            .Setup(pm => pm.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        var directoryService = new Mock<IDirectoryService>();
        var logger = new Mock<ILogger<MetadataScanTask>>();
        var config = new PluginConfiguration { MaxRefreshesPerRun = 1 };

        var task = new MetadataScanTask(libraryManager.Object, providerManager.Object, directoryService.Object, logger.Object, config);

        await task.Execute(new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            pm => pm.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Exactly(1));
    }
}
