using System.Collections.Generic;
using System.Linq;
using Jellyfin.Data.Enums;
using Kongflix.PosterScanner.Configuration;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Entities;

namespace Kongflix.PosterScanner.Scanning;

/// <summary>
/// Finds top-level movies and series that are missing a poster (primary image).
/// </summary>
public class PosterLibraryScanner
{
    private static readonly BaseItemKind[] ScannedItemKinds = { BaseItemKind.Movie, BaseItemKind.Series };

    private readonly ILibraryManager _libraryManager;

    /// <summary>
    /// Initializes a new instance of the <see cref="PosterLibraryScanner"/> class.
    /// </summary>
    /// <param name="libraryManager">Library manager.</param>
    public PosterLibraryScanner(ILibraryManager libraryManager)
    {
        _libraryManager = libraryManager;
    }

    /// <summary>
    /// Scans the libraries selected by <paramref name="config"/> for movies and
    /// series missing a poster. Only the item itself is checked — for a series
    /// this means the series entry, never its seasons or episodes.
    /// </summary>
    /// <param name="config">The plugin configuration.</param>
    /// <returns>The movies/series that have no primary image.</returns>
    public IReadOnlyList<BaseItem> FindItemsMissingPosters(PluginConfiguration config)
    {
        var libraries = _libraryManager.GetVirtualFolders();
        var libraryIds = LibrarySelector.ResolveLibraryIds(config, libraries);

        if (libraryIds.Count == 0)
        {
            return [];
        }

        var query = new InternalItemsQuery
        {
            TopParentIds = libraryIds.ToArray(),
            IncludeItemTypes = ScannedItemKinds,
            Recursive = true,
            IsVirtualItem = false,
        };

        return _libraryManager.GetItemList(query)
            .Where(item => !item.HasImage(ImageType.Primary, 0))
            .ToList();
    }
}
