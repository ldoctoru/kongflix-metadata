using System;
using System.Collections.Generic;
using System.Linq;
using Jellyfin.Data.Enums;
using Kongflix.PosterScanner.Configuration;
using Kongflix.PosterScanner.Scanning;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Entities;
using Moq;
using Xunit;

namespace Kongflix.PosterScanner.Tests;

public class PosterLibraryScannerTests
{
    private static BaseItem WithPoster(BaseItem item, bool hasPoster)
    {
        item.ImageInfos = hasPoster
            ? new[] { new ItemImageInfo { Type = ImageType.Primary, Path = "poster.jpg" } }
            : Array.Empty<ItemImageInfo>();
        return item;
    }

    [Fact]
    public void ReturnsOnlyItemsMissingAPrimaryImage()
    {
        var libraryId = Guid.NewGuid();
        var libraryManager = new Mock<ILibraryManager>();

        libraryManager.Setup(m => m.GetVirtualFolders()).Returns(new List<VirtualFolderInfo>
        {
            new() { ItemId = libraryId.ToString(), Name = "Movies", CollectionType = CollectionTypeOptions.movies },
        });

        var missingPoster = WithPoster(new Movie { Name = "Missing" }, hasPoster: false);
        var hasPoster = WithPoster(new Movie { Name = "HasPoster" }, hasPoster: true);

        InternalItemsQuery? capturedQuery = null;
        libraryManager
            .Setup(m => m.GetItemList(It.IsAny<InternalItemsQuery>()))
            .Callback<InternalItemsQuery>(q => capturedQuery = q)
            .Returns(new List<BaseItem> { missingPoster, hasPoster });

        var scanner = new PosterLibraryScanner(libraryManager.Object);
        var result = scanner.FindItemsMissingPosters(new PluginConfiguration());

        Assert.Single(result);
        Assert.Same(missingPoster, result[0]);

        Assert.NotNull(capturedQuery);
        Assert.Equal(new[] { libraryId }, capturedQuery!.TopParentIds);
        Assert.Equal(new[] { BaseItemKind.Movie, BaseItemKind.Series }, capturedQuery.IncludeItemTypes);
        Assert.True(capturedQuery.Recursive);
    }

    [Fact]
    public void NeverAsksForSeasonsOrEpisodes()
    {
        var libraryId = Guid.NewGuid();
        var libraryManager = new Mock<ILibraryManager>();

        libraryManager.Setup(m => m.GetVirtualFolders()).Returns(new List<VirtualFolderInfo>
        {
            new() { ItemId = libraryId.ToString(), Name = "Shows", CollectionType = CollectionTypeOptions.tvshows },
        });

        InternalItemsQuery? capturedQuery = null;
        libraryManager
            .Setup(m => m.GetItemList(It.IsAny<InternalItemsQuery>()))
            .Callback<InternalItemsQuery>(q => capturedQuery = q)
            .Returns(new List<BaseItem>());

        var scanner = new PosterLibraryScanner(libraryManager.Object);
        scanner.FindItemsMissingPosters(new PluginConfiguration());

        Assert.NotNull(capturedQuery);
        Assert.DoesNotContain(BaseItemKind.Season, capturedQuery!.IncludeItemTypes);
        Assert.DoesNotContain(BaseItemKind.Episode, capturedQuery.IncludeItemTypes);
    }

    [Fact]
    public void NoEligibleLibraries_ReturnsEmptyWithoutQueryingItems()
    {
        var libraryManager = new Mock<ILibraryManager>();
        libraryManager.Setup(m => m.GetVirtualFolders()).Returns(new List<VirtualFolderInfo>
        {
            new() { ItemId = Guid.NewGuid().ToString(), Name = "Music", CollectionType = CollectionTypeOptions.music },
        });

        var scanner = new PosterLibraryScanner(libraryManager.Object);
        var result = scanner.FindItemsMissingPosters(new PluginConfiguration());

        Assert.Empty(result);
        libraryManager.Verify(m => m.GetItemList(It.IsAny<InternalItemsQuery>()), Times.Never);
    }
}
