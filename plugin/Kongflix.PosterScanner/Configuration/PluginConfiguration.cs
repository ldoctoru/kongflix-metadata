using MediaBrowser.Model.Plugins;

namespace Kongflix.PosterScanner.Configuration;

/// <summary>
/// Configuration for the Kongflix Poster Scanner plugin.
/// </summary>
public class PluginConfiguration : BasePluginConfiguration
{
    /// <summary>
    /// Gets or sets the library ids (as strings) to scan. Empty means "not yet
    /// configured" — the scanner falls back to every library whose collection
    /// type isn't in <see cref="LibrarySelector.DefaultExcludedCollectionTypes"/>.
    /// </summary>
    public string[] IncludedLibraryIds { get; set; } = [];

    /// <summary>
    /// Gets or sets the maximum number of items refreshed in a single scan run.
    /// Items beyond this cap are left for the next run. 0 means unlimited.
    /// </summary>
    public int MaxItemsPerScan { get; set; } = 50;

    /// <summary>
    /// Gets or sets a value indicating whether a scan should only log what it
    /// would refresh, without actually triggering any metadata refresh.
    /// </summary>
    public bool DryRun { get; set; }
}
