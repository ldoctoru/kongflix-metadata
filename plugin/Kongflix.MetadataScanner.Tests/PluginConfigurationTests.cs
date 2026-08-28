using Kongflix.MetadataScanner.Configuration;
using Xunit;

namespace Kongflix.MetadataScanner.Tests;

public class PluginConfigurationTests
{
    [Fact]
    public void DefaultExcludeItemTypes_MatchesDocumentedDefault()
    {
        var config = new PluginConfiguration();
        Assert.Equal("Season,BoxSet,CollectionFolder,Audio,MusicAlbum,MusicArtist", config.ExcludeItemTypes);
    }

    [Fact]
    public void DefaultMaxRefreshesPerRun_Is200()
    {
        var config = new PluginConfiguration();
        Assert.Equal(200, config.MaxRefreshesPerRun);
    }
}
