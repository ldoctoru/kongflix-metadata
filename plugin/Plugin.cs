using System;
using System.Collections.Generic;
using Kongflix.MetadataScanner.Configuration;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Kongflix.MetadataScanner;

public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages
{
    public static readonly Guid PluginId = new Guid("5f3b2c1a-8e4d-4a6b-9c2f-1a2b3c4d5e6f");

    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    public static Plugin? Instance { get; private set; }

    public override string Name => "Kongflix Metadata Scanner";

    public override Guid Id => PluginId;

    public override string Description => "Scans the library for items missing a poster or overview and triggers Jellyfin's own metadata refresh for them.";

    public IEnumerable<PluginPageInfo> GetPages()
    {
        yield return new PluginPageInfo
        {
            Name = "KongflixMetadataScannerConfigPage",
            EmbeddedResourcePath = string.Format("{0}.Configuration.configPage.html", GetType().Namespace)
        };
    }
}
