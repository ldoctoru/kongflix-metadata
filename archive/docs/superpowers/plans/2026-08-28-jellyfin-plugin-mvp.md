# Jellyfin Plugin MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **⚠️ ENVIRONMENT WARNING — READ BEFORE EXECUTING:** This plan was authored in a sandbox with **no .NET SDK installed** (`dotnet` command not found). Every other plan in this repo relied on running the real test suite after each task to verify correctness; that verification loop is **not possible for this plan** in that same sandbox — no C# code in this plan has been compiled or run. If you are executing this plan in an environment WITHOUT a working `dotnet` CLI, every "Run: `dotnet build`" / "Run: `dotnet test`" step in this plan will fail with "command not found," not because the code is wrong. **Do not mark any task complete based on a task reviewer's read of the diff alone if `dotnet build`/`dotnet test` could not actually be executed** — that reviewer is validating shape and intent, not correctness. Jellyfin's Plugin SDK API surface (exact method names, `InternalItemsQuery` fields, `IScheduledTask` members) can differ slightly between SDK package versions; if a named API member doesn't exist when you actually build against the resolved NuGet package version, treat that as an expected, normal fix — adjust to match the real API and document the deviation, rather than treating it as a sign something else is wrong. This plan should be executed in (or the resulting code copied to and verified in) an environment with the .NET 8 SDK installed.

**Goal:** Build a Jellyfin plugin (C#/.NET) that runs as a Jellyfin Scheduled Task, scans the library for items missing a poster or overview (excluding configured item types), and triggers Jellyfin's own in-process metadata refresh for them — replacing the Docker/Python tool's core scan+refresh functionality.

**Architecture:** A standard Jellyfin plugin (`BasePlugin<PluginConfiguration>` + `IHasWebPages`) with one `IScheduledTask` implementation doing the scan/refresh work via `ILibraryManager`/`IProviderManager`, a `PluginConfiguration` holding exclude-types and refresh-cap settings, and a minimal HTML config page.

**Tech Stack:** C#, .NET 8, Jellyfin Plugin SDK (`Jellyfin.Controller`, `Jellyfin.Model` NuGet packages), xUnit + Moq for tests.

## Global Constraints

- Targets Jellyfin 10.9.x/10.10.x's plugin ABI — `net8.0` target framework.
- Default `ExcludeItemTypes`: `Season,BoxSet,CollectionFolder,Audio,MusicAlbum,MusicArtist` (comma-separated, whitespace-trimmed, empty entries dropped when parsed).
- Default `MaxRefreshesPerRun`: `200`.
- An item is "missing metadata" if `!item.HasImage(ImageType.Primary) || string.IsNullOrWhiteSpace(item.Overview)` — same OR-based criteria as the Docker app.
- Every `RefreshSingleItem` call must be individually try/caught — one item's failure must never stop the scan of remaining items.
- No custom cron/scheduling logic — scheduling is entirely Jellyfin's own `IScheduledTask` trigger system.
- No REST API calls, no API key — everything uses in-process Jellyfin services via constructor-injected interfaces.
- Project lives at `/plugin` in this repository, alongside the existing Python app (which is not modified or removed by this plan).

---

## File Structure

- `plugin/Kongflix.MetadataScanner.csproj` — project file.
- `plugin/Plugin.cs` — plugin entry point.
- `plugin/Configuration/PluginConfiguration.cs` — settings model.
- `plugin/Configuration/configPage.html` — admin config page.
- `plugin/Scanning/MissingMetadataChecker.cs` — pure predicate.
- `plugin/ScheduledTasks/MetadataScanTask.cs` — the scheduled task.
- `plugin/Kongflix.MetadataScanner.Tests/Kongflix.MetadataScanner.Tests.csproj` — test project.
- `plugin/Kongflix.MetadataScanner.Tests/MissingMetadataCheckerTests.cs`
- `plugin/Kongflix.MetadataScanner.Tests/MetadataScanTaskTests.cs`
- `plugin/Kongflix.MetadataScanner.Tests/PluginConfigurationTests.cs`
- `plugin/README.md` — build/install instructions.

---

### Task 1: Project scaffolding — plugin compiles and loads

**Files:**
- Create: `plugin/Kongflix.MetadataScanner.csproj`
- Create: `plugin/Plugin.cs`
- Create: `plugin/Configuration/PluginConfiguration.cs`
- Create: `plugin/Configuration/configPage.html`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `public class PluginConfiguration : BasePluginConfiguration` with `ExcludeItemTypes` (string) and `MaxRefreshesPerRun` (int) properties.
  - `public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages` — later tasks' `MetadataScanTask` will read `Plugin.Instance.Configuration`.

- [ ] **Step 1: Create the project file**

Create `plugin/Kongflix.MetadataScanner.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <RootNamespace>Kongflix.MetadataScanner</RootNamespace>
    <AssemblyVersion>1.0.0.0</AssemblyVersion>
    <FileVersion>1.0.0.0</FileVersion>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Jellyfin.Controller" Version="10.9.*" />
    <PackageReference Include="Jellyfin.Model" Version="10.9.*" />
  </ItemGroup>

  <ItemGroup>
    <EmbeddedResource Include="Configuration\configPage.html" />
  </ItemGroup>

</Project>
```

**Note:** `Version="10.9.*"` is a floating version intended to resolve to
the latest 10.9.x release on NuGet at restore time — this is the exact
kind of value that may need adjusting once actually restored against a
real NuGet feed and a real installed Jellyfin server version. If `10.9.*`
does not resolve or does not match your Jellyfin server's actual ABI
version, check the installed server's version (Dashboard → About) and
pin to the matching package version instead (e.g. `10.9.11`) — document
this as a deviation in your report if you change it.

- [ ] **Step 2: Create the plugin configuration model**

Create `plugin/Configuration/PluginConfiguration.cs`:

```csharp
using MediaBrowser.Model.Plugins;

namespace Kongflix.MetadataScanner.Configuration;

public class PluginConfiguration : BasePluginConfiguration
{
    public string ExcludeItemTypes { get; set; } = "Season,BoxSet,CollectionFolder,Audio,MusicAlbum,MusicArtist";

    public int MaxRefreshesPerRun { get; set; } = 200;
}
```

- [ ] **Step 3: Create the minimal config page**

Create `plugin/Configuration/configPage.html`:

```html
<!doctype html>
<html>
<head>
  <title>Kongflix Metadata Scanner</title>
</head>
<body>
  <div id="KongflixMetadataScannerConfigPage" data-role="page" class="page type-interior pluginConfigurationPage" data-require="emby-input,emby-button,emby-checkbox">
    <div data-role="content">
      <div class="content-primary">
        <form id="KongflixMetadataScannerConfigForm">
          <div class="inputContainer">
            <label class="inputLabel" for="ExcludeItemTypes">Exclude Item Types (comma-separated)</label>
            <input id="ExcludeItemTypes" name="ExcludeItemTypes" type="text" is="emby-input" />
            <div class="fieldDescription">e.g. Season,BoxSet,CollectionFolder,Audio,MusicAlbum,MusicArtist</div>
          </div>
          <div class="inputContainer">
            <label class="inputLabel" for="MaxRefreshesPerRun">Max Refreshes Per Run</label>
            <input id="MaxRefreshesPerRun" name="MaxRefreshesPerRun" type="number" is="emby-input" min="1" />
          </div>
          <button is="emby-button" type="submit" class="raised button-submit block emby-button">
            <span>Save</span>
          </button>
        </form>
      </div>
    </div>
  </div>
  <script type="text/javascript">
    (function () {
      var PluginConfig = {
        pluginUniqueId: "REPLACE-WITH-PLUGIN-GUID"
      };

      document.querySelector('#KongflixMetadataScannerConfigPage')
        .addEventListener('pageshow', function () {
          Dashboard.showLoadingMsg();
          ApiClient.getPluginConfiguration(PluginConfig.pluginUniqueId).then(function (config) {
            document.querySelector('#ExcludeItemTypes').value = config.ExcludeItemTypes;
            document.querySelector('#MaxRefreshesPerRun').value = config.MaxRefreshesPerRun;
            Dashboard.hideLoadingMsg();
          });
        });

      document.querySelector('#KongflixMetadataScannerConfigForm')
        .addEventListener('submit', function (e) {
          Dashboard.showLoadingMsg();
          ApiClient.getPluginConfiguration(PluginConfig.pluginUniqueId).then(function (config) {
            config.ExcludeItemTypes = document.querySelector('#ExcludeItemTypes').value;
            config.MaxRefreshesPerRun = parseInt(document.querySelector('#MaxRefreshesPerRun').value, 10);
            ApiClient.updatePluginConfiguration(PluginConfig.pluginUniqueId, config).then(function (result) {
              Dashboard.processPluginConfigurationUpdateResult(result);
            });
          });
          e.preventDefault();
          return false;
        });
    })();
  </script>
</body>
</html>
```

Note the placeholder `"REPLACE-WITH-PLUGIN-GUID"` — Step 4 defines the
real GUID; update this placeholder to match it exactly once that GUID
is chosen (do this in this same step, not a later one, so the file
never ships with the placeholder).

- [ ] **Step 4: Create the plugin entry point**

Create `plugin/Plugin.cs`. Generate a real GUID for `PluginId` (e.g. run
`[System.Guid]::NewGuid()` in PowerShell, `python3 -c "import uuid; print(uuid.uuid4())"`,
or any GUID generator) — do not reuse the example below verbatim in a
real deployment, but for this initial implementation it is fine to use
the example so the plan is concrete; note in your report if you
generated a fresh one instead (either is acceptable, but the same GUID
value must appear in both this file and `configPage.html`'s
`pluginUniqueId`):

```csharp
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
```

Update `configPage.html`'s `pluginUniqueId` placeholder to
`"5f3b2c1a-8e4d-4a6b-9c2f-1a2b3c4d5e6f"` (matching `PluginId` above) if
you used the example GUID, or to your freshly generated GUID if you
generated one instead.

- [ ] **Step 5: Attempt to build**

Run: `cd plugin && dotnet restore && dotnet build`

Expected: build succeeds. If it fails because `Jellyfin.Controller`/
`Jellyfin.Model` package versions don't resolve, or because a
referenced type/namespace (`BasePlugin<T>`, `IHasWebPages`,
`BasePluginConfiguration`, `IApplicationPaths`, `IXmlSerializer`,
`PluginPageInfo`) doesn't exist in the resolved package version, this
is expected per this plan's environment warning — adjust the package
version and/or `using` namespaces to match what actually resolves, and
document what you changed and why in your report. Do not proceed to
Step 6 until this actually compiles.

- [ ] **Step 6: Commit**

```bash
git add plugin/Kongflix.MetadataScanner.csproj plugin/Plugin.cs plugin/Configuration/PluginConfiguration.cs plugin/Configuration/configPage.html
git commit -m "feat: scaffold Jellyfin plugin project"
```

---

### Task 2: Missing-metadata predicate and tests

**Files:**
- Create: `plugin/Scanning/MissingMetadataChecker.cs`
- Create: `plugin/Kongflix.MetadataScanner.Tests/Kongflix.MetadataScanner.Tests.csproj`
- Create: `plugin/Kongflix.MetadataScanner.Tests/MissingMetadataCheckerTests.cs`

**Interfaces:**
- Consumes: `MediaBrowser.Controller.Entities.BaseItem` (Jellyfin SDK type — has `HasImage(ImageType)` and `Overview` members).
- Produces: `public static bool MissingMetadataChecker.IsMissingMetadata(BaseItem item)`.

- [ ] **Step 1: Create the test project**

Create `plugin/Kongflix.MetadataScanner.Tests/Kongflix.MetadataScanner.Tests.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <IsPackable>false</IsPackable>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.*" />
    <PackageReference Include="xunit" Version="2.*" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.*" />
    <PackageReference Include="Moq" Version="4.*" />
  </ItemGroup>

  <ItemGroup>
    <ProjectReference Include="..\Kongflix.MetadataScanner.csproj" />
  </ItemGroup>

</Project>
```

- [ ] **Step 2: Write the failing tests**

Create `plugin/Kongflix.MetadataScanner.Tests/MissingMetadataCheckerTests.cs`.

Jellyfin's `BaseItem` is an abstract base class from the SDK — for a
unit test, use the simplest concrete subclass available in the SDK that
lets you set `Overview` and control `HasImage` (Jellyfin's `Movie` class
is a common concrete `BaseItem` subclass used in community plugin
tests). `HasImage(ImageType.Primary)` is derived from whether the item
has an entry of that type in its internal image list — check the SDK's
actual API for how tests typically set this (e.g. a `SetImage` method,
or an `ImageInfos` collection you can populate directly with an
`ItemImageInfo`). If the exact mechanism differs from what's sketched
below once you're working against the real package, adjust and
document the deviation — the important thing is that the test
constructs an item that genuinely reports `HasImage(ImageType.Primary)`
as `true` or `false` as needed, not that it uses this exact API call:

```csharp
using System;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Model.Entities;
using Xunit;

namespace Kongflix.MetadataScanner.Tests;

public class MissingMetadataCheckerTests
{
    private static Movie MakeItem(bool hasPoster, string? overview)
    {
        var item = new Movie
        {
            Name = "Test Item",
            Overview = overview,
        };

        if (hasPoster)
        {
            item.ImageInfos = new[]
            {
                new ItemImageInfo
                {
                    Path = "/fake/poster.jpg",
                    Type = ImageType.Primary,
                }
            };
        }

        return item;
    }

    [Fact]
    public void CompleteItem_IsNotMissing()
    {
        var item = MakeItem(hasPoster: true, overview: "A great movie about things.");
        Assert.False(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }

    [Fact]
    public void MissingPoster_IsFlagged()
    {
        var item = MakeItem(hasPoster: false, overview: "A great movie about things.");
        Assert.True(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }

    [Fact]
    public void MissingOverview_IsFlagged()
    {
        var item = MakeItem(hasPoster: true, overview: null);
        Assert.True(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }

    [Fact]
    public void EmptyOverviewString_IsFlagged()
    {
        var item = MakeItem(hasPoster: true, overview: "");
        Assert.True(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }

    [Fact]
    public void WhitespaceOnlyOverview_IsFlagged()
    {
        var item = MakeItem(hasPoster: true, overview: "   ");
        Assert.True(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }

    [Fact]
    public void MissingBoth_IsFlagged()
    {
        var item = MakeItem(hasPoster: false, overview: null);
        Assert.True(Scanning.MissingMetadataChecker.IsMissingMetadata(item));
    }
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd plugin/Kongflix.MetadataScanner.Tests && dotnet test`
Expected: FAIL to compile — `MissingMetadataChecker` doesn't exist yet.

- [ ] **Step 4: Write minimal implementation**

Create `plugin/Scanning/MissingMetadataChecker.cs`:

```csharp
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `dotnet test`
Expected: PASS (6 tests). If `Movie`'s `ImageInfos` property or
`ItemImageInfo`'s shape don't match what's used above once built
against the real package, adjust the test's item-construction helper
to whatever the real SDK requires — document the deviation.

- [ ] **Step 6: Commit**

```bash
git add plugin/Scanning/MissingMetadataChecker.cs plugin/Kongflix.MetadataScanner.Tests/Kongflix.MetadataScanner.Tests.csproj plugin/Kongflix.MetadataScanner.Tests/MissingMetadataCheckerTests.cs
git commit -m "feat: add missing-metadata predicate"
```

---

### Task 3: Scheduled task — scan and refresh

**Files:**
- Create: `plugin/ScheduledTasks/MetadataScanTask.cs`
- Create: `plugin/Kongflix.MetadataScanner.Tests/MetadataScanTaskTests.cs`

**Interfaces:**
- Consumes:
  - `MissingMetadataChecker.IsMissingMetadata(BaseItem item) -> bool` (Task 2)
  - `Plugin.Instance.Configuration.ExcludeItemTypes: string`, `Plugin.Instance.Configuration.MaxRefreshesPerRun: int` (Task 1)
  - `MediaBrowser.Controller.Library.ILibraryManager`, `MediaBrowser.Controller.Providers.IProviderManager`, `MediaBrowser.Controller.IO.IDirectoryService` (Jellyfin SDK interfaces, injected via constructor)
- Produces: `public class MetadataScanTask : IScheduledTask` with a public `Execute(IProgress<double>, CancellationToken)` method other code (none yet in this plan) could call directly for testing.

This task has the highest risk of needing adjustment against the real
SDK, since `ILibraryManager`'s exact query method/type names
(`GetItemList` vs `GetItemsResult`, `InternalItemsQuery`'s exact
property names for excluding types) can vary by SDK version. Treat any
compile error here as expected per the plan's environment warning.

- [ ] **Step 1: Write the failing tests**

Create `plugin/Kongflix.MetadataScanner.Tests/MetadataScanTaskTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Kongflix.MetadataScanner.Configuration;
using Kongflix.MetadataScanner.ScheduledTasks;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.IO;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Providers;
using Microsoft.Extensions.Logging;
using Moq;
using Xunit;

namespace Kongflix.MetadataScanner.Tests;

public class MetadataScanTaskTests
{
    private static Movie MakeFlaggedItem(string id)
    {
        return new Movie
        {
            Id = Guid.NewGuid(),
            Name = id,
            Overview = null,
        };
    }

    [Fact]
    public async Task Execute_RefreshesOnlyFlaggedItems()
    {
        var complete = new Movie { Id = Guid.NewGuid(), Name = "Complete", Overview = "ok" };
        complete.ImageInfos = new[] { new MediaBrowser.Model.Entities.ItemImageInfo { Path = "/x.jpg", Type = MediaBrowser.Model.Entities.ImageType.Primary } };
        var missing1 = MakeFlaggedItem("Missing1");
        var missing2 = MakeFlaggedItem("Missing2");

        var libraryManager = new Mock<ILibraryManager>();
        libraryManager
            .Setup(lm => lm.GetItemList(It.IsAny<InternalItemsQuery>()))
            .Returns(new List<BaseItem> { complete, missing1, missing2 });

        var providerManager = new Mock<IProviderManager>();
        providerManager
            .Setup(pm => pm.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        var directoryService = new Mock<IDirectoryService>();
        var logger = new Mock<ILogger<MetadataScanTask>>();

        var config = new PluginConfiguration { MaxRefreshesPerRun = 200 };
        // If Plugin.Instance is required by MetadataScanTask, this test may need
        // a way to inject config directly instead of via the static singleton —
        // if so, adjust MetadataScanTask's constructor to accept PluginConfiguration
        // directly (preferred for testability) rather than reading Plugin.Instance,
        // and update this test and Task 3's Step 4 implementation accordingly.

        var task = new MetadataScanTask(libraryManager.Object, providerManager.Object, directoryService.Object, logger.Object, config);

        await task.Execute(new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            pm => pm.RefreshSingleItem(missing1, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Once);
        providerManager.Verify(
            pm => pm.RefreshSingleItem(missing2, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Once);
        providerManager.Verify(
            pm => pm.RefreshSingleItem(complete, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task Execute_IsolatesPerItemFailures()
    {
        var bad = MakeFlaggedItem("Bad");
        var good = MakeFlaggedItem("Good");

        var libraryManager = new Mock<ILibraryManager>();
        libraryManager
            .Setup(lm => lm.GetItemList(It.IsAny<InternalItemsQuery>()))
            .Returns(new List<BaseItem> { bad, good });

        var providerManager = new Mock<IProviderManager>();
        providerManager
            .Setup(pm => pm.RefreshSingleItem(bad, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("boom"));
        providerManager
            .Setup(pm => pm.RefreshSingleItem(good, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        var directoryService = new Mock<IDirectoryService>();
        var logger = new Mock<ILogger<MetadataScanTask>>();
        var config = new PluginConfiguration { MaxRefreshesPerRun = 200 };

        var task = new MetadataScanTask(libraryManager.Object, providerManager.Object, directoryService.Object, logger.Object, config);

        // Must not throw, despite "bad" failing.
        await task.Execute(new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            pm => pm.RefreshSingleItem(good, It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task Execute_StopsAtMaxRefreshesPerRun()
    {
        var items = new List<BaseItem>
        {
            MakeFlaggedItem("1"),
            MakeFlaggedItem("2"),
            MakeFlaggedItem("3"),
        };

        var libraryManager = new Mock<ILibraryManager>();
        libraryManager
            .Setup(lm => lm.GetItemList(It.IsAny<InternalItemsQuery>()))
            .Returns(items);

        var providerManager = new Mock<IProviderManager>();
        providerManager
            .Setup(pm => pm.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        var directoryService = new Mock<IDirectoryService>();
        var logger = new Mock<ILogger<MetadataScanTask>>();
        var config = new PluginConfiguration { MaxRefreshesPerRun = 1 };

        var task = new MetadataScanTask(libraryManager.Object, providerManager.Object, directoryService.Object, logger.Object, config);

        await task.Execute(new Progress<double>(), CancellationToken.None);

        providerManager.Verify(
            pm => pm.RefreshSingleItem(It.IsAny<BaseItem>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<CancellationToken>()),
            Times.Exactly(1));
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test`
Expected: FAIL to compile — `MetadataScanTask` doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `plugin/ScheduledTasks/MetadataScanTask.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Kongflix.MetadataScanner.Configuration;
using Kongflix.MetadataScanner.Scanning;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.IO;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Tasks;
using Microsoft.Extensions.Logging;

namespace Kongflix.MetadataScanner.ScheduledTasks;

public class MetadataScanTask : IScheduledTask
{
    private readonly ILibraryManager _libraryManager;
    private readonly IProviderManager _providerManager;
    private readonly IDirectoryService _directoryService;
    private readonly ILogger<MetadataScanTask> _logger;
    private readonly PluginConfiguration _config;

    public MetadataScanTask(
        ILibraryManager libraryManager,
        IProviderManager providerManager,
        IDirectoryService directoryService,
        ILogger<MetadataScanTask> logger,
        PluginConfiguration? config = null)
    {
        _libraryManager = libraryManager;
        _providerManager = providerManager;
        _directoryService = directoryService;
        _logger = logger;
        _config = config ?? Plugin.Instance!.Configuration;
    }

    public string Name => "Scan for Missing Metadata";

    public string Key => "KongflixMetadataScan";

    public string Description => "Scans the library for items missing a poster or overview and triggers a metadata refresh for them.";

    public string Category => "Library";

    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers()
    {
        yield return new TaskTriggerInfo
        {
            Type = TaskTriggerInfo.TriggerDaily,
            TimeOfDayTicks = TimeSpan.FromHours(3).Ticks,
        };
    }

    public async Task Execute(IProgress<double> progress, CancellationToken cancellationToken)
    {
        var excludeTypes = (_config.ExcludeItemTypes ?? string.Empty)
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .ToList();

        var query = new InternalItemsQuery
        {
            Recursive = true,
        };
        if (excludeTypes.Count > 0)
        {
            // NOTE: InternalItemsQuery's exact property for excluding by type
            // name may differ (e.g. ExcludeItemTypes taking BaseItemKind[]
            // rather than string[]) — adjust to match the real SDK type here.
            query.ExcludeItemTypes = excludeTypes.ToArray();
        }

        var items = _libraryManager.GetItemList(query);
        var flaggedItems = items.Where(MissingMetadataChecker.IsMissingMetadata).ToList();

        var itemsToRefresh = flaggedItems.Take(_config.MaxRefreshesPerRun).ToList();

        var refreshed = 0;
        var failed = 0;
        var processed = 0;

        foreach (var item in itemsToRefresh)
        {
            cancellationToken.ThrowIfCancellationRequested();

            try
            {
                var options = new MetadataRefreshOptions(_directoryService)
                {
                    MetadataRefreshMode = MediaBrowser.Controller.Providers.MetadataRefreshMode.FullRefresh,
                    ImageRefreshMode = MediaBrowser.Controller.Providers.MetadataRefreshMode.FullRefresh,
                    ReplaceAllMetadata = false,
                    ReplaceAllImages = false,
                };
                await _providerManager.RefreshSingleItem(item, options, cancellationToken).ConfigureAwait(false);
                refreshed++;
            }
            catch (Exception error)
            {
                failed++;
                _logger.LogError(error, "Failed to refresh item {ItemName}", item.Name);
            }

            processed++;
            progress.Report(100.0 * processed / Math.Max(1, itemsToRefresh.Count));
        }

        var skipped = flaggedItems.Count - itemsToRefresh.Count;
        _logger.LogInformation(
            "Kongflix metadata scan complete: scanned={Scanned} flagged={Flagged} refreshed={Refreshed} failed={Failed} skipped={Skipped}",
            items.Count,
            flaggedItems.Count,
            refreshed,
            failed,
            skipped);
    }
}
```

Note the two inline comments flagging likely SDK-surface adjustments
(`ExcludeItemTypes` property shape, and confirm `MetadataRefreshMode`'s
exact enum location) — resolve these against the actually-restored
package and remove the comments once confirmed correct, documenting
what changed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test`
Expected: PASS (3 tests in this file). Adjust mock setups/assertions if
the real `ILibraryManager`/`IProviderManager` interface members differ
from what's used above (e.g. `GetItemList` might be named differently,
or return a wrapper type instead of `List<BaseItem>` directly) —
document any such deviation.

- [ ] **Step 5: Commit**

```bash
git add plugin/ScheduledTasks/MetadataScanTask.cs plugin/Kongflix.MetadataScanner.Tests/MetadataScanTaskTests.cs
git commit -m "feat: add scheduled task for scanning and refreshing"
```

---

### Task 4: Plugin configuration tests and README

**Files:**
- Create: `plugin/Kongflix.MetadataScanner.Tests/PluginConfigurationTests.cs`
- Create: `plugin/README.md`

**Interfaces:**
- Consumes: `PluginConfiguration` (Task 1).
- Produces: nothing new — tests and docs only.

- [ ] **Step 1: Write the tests**

Create `plugin/Kongflix.MetadataScanner.Tests/PluginConfigurationTests.cs`:

```csharp
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `dotnet test`
Expected: PASS (2 tests in this file; full suite should now be 11 tests
total across all three test files — 6 + 3 + 2).

- [ ] **Step 3: Write the README**

Create `plugin/README.md`:

```markdown
# Kongflix Metadata Scanner (Jellyfin Plugin)

A native Jellyfin plugin that scans your library for items missing a
poster or overview and triggers Jellyfin's own metadata refresh for
them — the in-process successor to the standalone Docker-based
kongflix-metadata tool.

## Building

Requires the .NET 8 SDK.

```bash
cd plugin
dotnet restore
dotnet build --configuration Release
dotnet test
```

## Installing (manual, local build)

1. Build the project in Release mode (see above).
2. Copy the built output (`bin/Release/net8.0/Kongflix.MetadataScanner.dll`
   and any dependent DLLs not already present in Jellyfin's own
   `System` folder) into a new folder under Jellyfin's plugin
   directory, e.g. `<jellyfin-data>/plugins/Kongflix Metadata Scanner/`.
3. Restart Jellyfin.
4. In Jellyfin's Dashboard → Plugins, confirm "Kongflix Metadata
   Scanner" is listed and enabled.
5. In Dashboard → Scheduled Tasks, find "Scan for Missing Metadata"
   under the Library category — you can run it on demand or adjust its
   trigger (default: daily at 3 AM).
6. In Dashboard → Plugins → Kongflix Metadata Scanner, configure
   `Exclude Item Types` and `Max Refreshes Per Run` as needed.

## What it does

Scans all library items except the configured excluded types (default:
`Season, BoxSet, CollectionFolder, Audio, MusicAlbum, MusicArtist`).
An item is flagged if it has no poster image or no overview/plot text.
Flagged items (up to `Max Refreshes Per Run` per scan) get a full
metadata refresh requested via Jellyfin's own `IProviderManager` —
Jellyfin's configured providers (TMDb, TVDB, etc.) do the actual
lookup. A per-item failure is logged and does not stop the rest of the
scan.

## Status

MVP: scan + refresh + basic config. Not yet built: a missing-items
list/history view, per-item manual retry, and a real-time
newly-added-item watcher (planned as follow-up work, matching the
Docker app's feature set incrementally).
```

- [ ] **Step 4: Commit**

```bash
git add plugin/Kongflix.MetadataScanner.Tests/PluginConfigurationTests.cs plugin/README.md
git commit -m "test: add plugin configuration tests; add plugin README"
```

---

### Task 5: Manual verification in a real Jellyfin server

**Files:**
- None (manual verification task, no code changes).

**Interfaces:**
- Consumes: the full plugin build (Tasks 1-4).
- Produces: confidence the plugin actually loads and runs inside a real Jellyfin server — this environment could not verify any of this.

- [ ] **Step 1: Build in Release mode in an environment with the .NET 8 SDK**

```bash
cd plugin
dotnet restore
dotnet build --configuration Release
dotnet test
```

Expected: all tests pass. If they don't, work through the compile/test
failures against the real SDK — per this plan's environment warning,
some adjustment here is expected, not a sign of a fundamentally wrong
plan.

- [ ] **Step 2: Install into a real (ideally test/non-production) Jellyfin server**

Follow `plugin/README.md`'s install steps. Restart Jellyfin.

- [ ] **Step 3: Verify the plugin loads**

Dashboard → Plugins → confirm "Kongflix Metadata Scanner" appears,
enabled, with no load errors in Jellyfin's log.

- [ ] **Step 4: Verify the config page**

Dashboard → Plugins → Kongflix Metadata Scanner → confirm the config
page loads, shows the default values, and Save persists a changed
value (reload the page and confirm the change stuck).

- [ ] **Step 5: Verify the scheduled task runs**

Dashboard → Scheduled Tasks → find "Scan for Missing Metadata" →
run it manually → confirm it completes successfully in the task
history, and check Jellyfin's log for the summary line
(`scanned=... flagged=... refreshed=... failed=... skipped=...`).

- [ ] **Step 6: Spot-check a refreshed item**

Pick an item that was flagged and refreshed; confirm in Jellyfin's UI
whether it now has a poster/overview (subject to the same real-world
caveat as the Docker app: Jellyfin's own providers may simply have no
data for a given item, which is not something this plugin controls).

- [ ] **Step 7: Record results**

No commit needed for this task — it's verification only. If any step
surfaces a bug (including SDK API mismatches not caught during
Tasks 1-4), open a follow-up task/fix and re-run the affected step.
