using System;
using System.Collections.Generic;
using Kongflix.PosterScanner.Configuration;
using Kongflix.PosterScanner.Scanning;
using MediaBrowser.Model.Entities;
using Xunit;

namespace Kongflix.PosterScanner.Tests;

public class LibrarySelectorTests
{
    private static VirtualFolderInfo Library(string itemId, CollectionTypeOptions? type)
    {
        return new VirtualFolderInfo
        {
            ItemId = itemId,
            Name = itemId,
            CollectionType = type,
        };
    }

    [Fact]
    public void WithNoSavedSelection_IncludesMoviesTvShowsAndMixedLibraries()
    {
        var movies = Guid.NewGuid();
        var tvShows = Guid.NewGuid();
        var mixed = Guid.NewGuid();
        var music = Guid.NewGuid();
        var books = Guid.NewGuid();

        var libraries = new List<VirtualFolderInfo>
        {
            Library(movies.ToString(), CollectionTypeOptions.movies),
            Library(tvShows.ToString(), CollectionTypeOptions.tvshows),
            Library(mixed.ToString(), null),
            Library(music.ToString(), CollectionTypeOptions.music),
            Library(books.ToString(), CollectionTypeOptions.books),
        };

        var result = LibrarySelector.ResolveLibraryIds(new PluginConfiguration(), libraries);

        Assert.Contains(movies, result);
        Assert.Contains(tvShows, result);
        Assert.Contains(mixed, result);
        Assert.DoesNotContain(music, result);
        Assert.DoesNotContain(books, result);
    }

    [Fact]
    public void WithSavedSelection_OnlyReturnsExplicitlyPickedLibraries()
    {
        var picked = Guid.NewGuid();
        var notPicked = Guid.NewGuid();

        var libraries = new List<VirtualFolderInfo>
        {
            Library(picked.ToString(), CollectionTypeOptions.movies),
            Library(notPicked.ToString(), CollectionTypeOptions.movies),
        };

        var config = new PluginConfiguration
        {
            IncludedLibraryIds = new[] { picked.ToString() },
        };

        var result = LibrarySelector.ResolveLibraryIds(config, libraries);

        Assert.Single(result);
        Assert.Contains(picked, result);
    }

    [Fact]
    public void IgnoresUnparsableSavedIds()
    {
        var config = new PluginConfiguration
        {
            IncludedLibraryIds = new[] { "not-a-guid" },
        };

        var result = LibrarySelector.ResolveLibraryIds(config, new List<VirtualFolderInfo>());

        Assert.Empty(result);
    }
}
