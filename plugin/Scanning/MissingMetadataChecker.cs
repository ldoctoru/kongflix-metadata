using MediaBrowser.Controller.Entities;
using MediaBrowser.Model.Entities;

namespace Kongflix.MetadataScanner.Scanning;

public static class MissingMetadataChecker
{
    public static bool IsMissingMetadata(BaseItem item)
    {
        var hasPoster = item.HasImage(ImageType.Primary);
        var hasOverview = !string.IsNullOrWhiteSpace(item.Overview);
        return !hasPoster || !hasOverview;
    }
}
