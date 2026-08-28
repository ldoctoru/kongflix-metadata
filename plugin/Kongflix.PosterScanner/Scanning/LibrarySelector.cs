using System;
using System.Collections.Generic;
using System.Linq;
using Kongflix.PosterScanner.Configuration;
using MediaBrowser.Model.Entities;

namespace Kongflix.PosterScanner.Scanning;

/// <summary>
/// Resolves which libraries a poster scan should cover.
/// </summary>
public static class LibrarySelector
{
    /// <summary>
    /// Collection types that are never scanned unless explicitly picked in
    /// <see cref="PluginConfiguration.IncludedLibraryIds"/> — music, books
    /// and home videos have no comparable "poster" concept for this scan.
    /// </summary>
    public static readonly IReadOnlySet<CollectionTypeOptions> DefaultExcludedCollectionTypes =
        new HashSet<CollectionTypeOptions>
        {
            CollectionTypeOptions.music,
            CollectionTypeOptions.musicvideos,
            CollectionTypeOptions.homevideos,
            CollectionTypeOptions.boxsets,
            CollectionTypeOptions.books,
        };

    /// <summary>
    /// Resolves the ids of the libraries a scan should cover: the explicit
    /// picks from configuration when any were saved, otherwise every library
    /// whose collection type isn't in <see cref="DefaultExcludedCollectionTypes"/>
    /// (movies, tvshows, and mixed/untyped libraries).
    /// </summary>
    /// <param name="config">The plugin configuration.</param>
    /// <param name="libraries">The server's virtual folders (libraries).</param>
    /// <returns>The ids of the libraries to scan.</returns>
    public static IReadOnlyList<Guid> ResolveLibraryIds(PluginConfiguration config, IReadOnlyList<VirtualFolderInfo> libraries)
    {
        ArgumentNullException.ThrowIfNull(config);
        ArgumentNullException.ThrowIfNull(libraries);

        if (config.IncludedLibraryIds is { Length: > 0 })
        {
            return config.IncludedLibraryIds
                .Select(id => Guid.TryParse(id, out var guid) ? (Guid?)guid : null)
                .Where(guid => guid.HasValue)
                .Select(guid => guid!.Value)
                .Distinct()
                .ToList();
        }

        return libraries
            .Where(IsEligibleByDefault)
            .Select(library => Guid.Parse(library.ItemId))
            .ToList();
    }

    private static bool IsEligibleByDefault(VirtualFolderInfo library)
    {
        // No collection type, or the explicit "mixed content" type, both mean
        // a general-purpose library that can contain movies/series.
        return library.CollectionType is null
            || !DefaultExcludedCollectionTypes.Contains(library.CollectionType.Value);
    }
}
