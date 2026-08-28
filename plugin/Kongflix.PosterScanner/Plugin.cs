using System;
using System.Collections.Generic;
using Kongflix.PosterScanner.Configuration;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Kongflix.PosterScanner;

/// <summary>
/// The Kongflix Poster Scanner plugin entry point.
/// </summary>
public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages
{
    /// <summary>
    /// The plugin's fixed unique id.
    /// </summary>
    public static readonly Guid PluginId = new("8b5a1c2d-4f6e-4a3b-9d1c-2e3f4a5b6c7d");

    /// <summary>
    /// Initializes a new instance of the <see cref="Plugin"/> class.
    /// </summary>
    /// <param name="applicationPaths">Application paths.</param>
    /// <param name="xmlSerializer">Xml serializer.</param>
    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    /// <summary>
    /// Gets the running plugin instance.
    /// </summary>
    public static Plugin? Instance { get; private set; }

    /// <inheritdoc />
    public override string Name => "Kongflix Poster Scanner";

    /// <inheritdoc />
    public override Guid Id => PluginId;

    /// <inheritdoc />
    public override string Description =>
        "Scans movie and series libraries for items missing a poster and forces Jellyfin's agents to refresh them.";

    /// <inheritdoc />
    public IEnumerable<PluginPageInfo> GetPages()
    {
        yield return new PluginPageInfo
        {
            Name = "KongflixPosterScannerConfigPage",
            EmbeddedResourcePath = string.Format("{0}.Configuration.configPage.html", GetType().Namespace)
        };
    }
}
