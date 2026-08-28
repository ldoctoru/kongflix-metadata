using Kongflix.PosterScanner.Configuration;
using Xunit;

namespace Kongflix.PosterScanner.Tests;

public class PluginConfigurationTests
{
    [Fact]
    public void DefaultsAreSaneOutOfTheBox()
    {
        var config = new PluginConfiguration();

        Assert.Empty(config.IncludedLibraryIds);
        Assert.Equal(50, config.MaxItemsPerScan);
        Assert.False(config.DryRun);
    }
}
