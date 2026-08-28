using MediaBrowser.Model.Plugins;

namespace Kongflix.MetadataScanner.Configuration;

public class PluginConfiguration : BasePluginConfiguration
{
    public string ExcludeItemTypes { get; set; } = "Season,BoxSet,CollectionFolder,Audio,MusicAlbum,MusicArtist";

    public int MaxRefreshesPerRun { get; set; } = 200;
}
