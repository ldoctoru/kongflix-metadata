using System;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Model.Entities;
using Xunit;

namespace Kongflix.MetadataScanner.Tests;

public class MissingMetadataCheckerTests
{
    private static Movie MakeItem(bool hasPoster, string? overview)
    {
        var item = new Movie
        {
            Name = "Test Item",
            Overview = overview,
        };

        if (hasPoster)
        {
            item.ImageInfos = new[]
            {
                new ItemImageInfo
                {
                    Path = "/fake/poster.jpg",
                    Type = ImageType.Primary,
                }
            };
        }

        return item;
    }

    [Fact]
    public void CompleteItem_IsNotMissing()
    {
        var item = MakeItem(hasPoster: true, overview: "A great movie about things.");
        Assert.False(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }

    [Fact]
    public void MissingPoster_IsFlagged()
    {
        var item = MakeItem(hasPoster: false, overview: "A great movie about things.");
        Assert.True(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }

    [Fact]
    public void MissingOverview_IsFlagged()
    {
        var item = MakeItem(hasPoster: true, overview: null);
        Assert.True(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }

    [Fact]
    public void EmptyOverviewString_IsFlagged()
    {
        var item = MakeItem(hasPoster: true, overview: "");
        Assert.True(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }

    [Fact]
    public void WhitespaceOnlyOverview_IsFlagged()
    {
        var item = MakeItem(hasPoster: true, overview: "   ");
        Assert.True(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }

    [Fact]
    public void MissingBoth_IsFlagged()
    {
        var item = MakeItem(hasPoster: false, overview: null);
        Assert.True(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }
}
