# amplifier-module-resolution

**Module source resolution with pluggable strategies for Amplifier applications**

amplifier-module-resolution provides standard implementations of amplifier-core's ModuleSource and ModuleSourceResolver protocols. It implements a 5-layer resolution strategy using uv for git operations, supports file/git/package sources, and integrates with settings-based overrides.

---

## Documentation

- **[Quick Start](#quick-start)** - Get started in 5 minutes
- **[API Reference](#api-reference)** - Complete API documentation
- **[User Guide](docs/USER_GUIDE.md)** - Customizing module sources
- **[Technical Specification](docs/SPECIFICATION.md)** - Resolution strategy and contracts
- **[Design Philosophy](#design-philosophy)** - Why this is a library, not kernel

---

## Installation

```bash
# Install uv first (required for GitSource and recommended for all Python work)
curl -LsSf https://astral.sh/uv/install.sh | sh

# From PyPI (when published)
uv pip install amplifier-module-resolution

# From git (development)
uv pip install git+https://github.com/microsoft/amplifier-module-resolution@main

# For local development
cd amplifier-module-resolution
uv pip install -e .

# Or using uv sync for development with dependencies
uv sync --dev
```

---

## Quick Start

```python
from amplifier_module_resolution import (
    StandardModuleSourceResolver,
    GitSource,
    FileSource,
)
from amplifier_config import ConfigManager
from pathlib import Path

# Set up settings provider for overrides
config = ConfigManager(paths=cli_paths)

# Create standard resolver
resolver = StandardModuleSourceResolver(
    workspace_dir=Path(".amplifier/modules"),  # Layer 2
    settings_provider=config,                   # Layers 3-4
)

# Resolve module to source
source = resolver.resolve("provider-anthropic")
# Uses 5-layer resolution: env → workspace → settings → profile → package

# Resolve module path
module_path = source.resolve()

print(f"Module at: {module_path}")
```

---

## What This Library Provides

### Important: Why This Is a Library (Not Kernel)

**From KERNEL_PHILOSOPHY.md**: "Could two teams want different behavior?"

**Answer for module resolution**: **YES**

Different applications need different resolution strategies:

| Application | Resolution Strategy | Source Types |
|-------------|---------------------|--------------|
| **CLI** | env → workspace → settings → profile → package | git (uv), file, package |
| **Web** | database → HTTP registry → cache | HTTP zip, database blob |
| **Enterprise** | corporate mirror → local cache → fail | Artifact server API |
| **Air-gapped** | local cache only → fail | File copy only |

**Conclusion**: Module resolution is **policy** (varies by app) → stays in **library** (not kernel).

**After web UI exists**: Revisit for potential kernel promotion if patterns converge (>80% similarity).

**Current status**: Library provides standard implementation; apps can create custom resolvers.

### Standard 5-Layer Resolution

The `StandardModuleSourceResolver` implements a comprehensive fallback strategy:

```
┌──────────────────────────────────────────────────────────┐
│ 1. ENVIRONMENT VARIABLE (highest precedence)             │
│    AMPLIFIER_MODULE_<ID>=<source-uri>                    │
│    → Temporary overrides, debugging                      │
├──────────────────────────────────────────────────────────┤
│ 2. WORKSPACE CONVENTION                                   │
│    .amplifier/modules/<module-id>/                       │
│    → Local development, active module work               │
├──────────────────────────────────────────────────────────┤
│ 3. SETTINGS PROVIDER                                      │
│    .amplifier/settings.yaml (project)                    │
│    ~/.amplifier/settings.yaml (user)                     │
│    → Project-wide or user-global overrides               │
├──────────────────────────────────────────────────────────┤
│ 4. PROFILE HINT                                           │
│    profile.tools[].source field                          │
│    → Profile-specified default sources                   │
├──────────────────────────────────────────────────────────┤
│ 5. INSTALLED PACKAGE (lowest precedence)                 │
│    importlib.metadata lookup                             │
│    → Pre-installed standard modules                      │
└──────────────────────────────────────────────────────────┘

First match wins - resolution stops at first layer that succeeds.
```

**→ See [Resolution Strategy Specification](docs/SPECIFICATION.md#resolution-order-5-layers) for complete technical details.**

**Quick example**:
```python
# Environment override takes highest precedence
export AMPLIFIER_MODULE_PROVIDER_ANTHROPIC="file:///home/dev/custom"

# Or use workspace for local development
.amplifier/modules/provider-anthropic/  # Auto-detected
```

### Source Types

#### FileSource

Local directory for development:

```python
from amplifier_module_resolution import FileSource

# Absolute path
source = FileSource("/home/dev/my-provider")

# Relative path (resolved to absolute)
source = FileSource("../my-provider")

# URI format
source = FileSource("file:///home/dev/my-provider")

# Resolve to module path (validates exists and is directory)
module_path = source.resolve()
```

**Use case**: Local development, testing, custom modules.

**Note**: FileSource validates the path exists and contains Python files during resolve().

#### GitSource

Git repository via uv:

```python
from amplifier_module_resolution import GitSource

# From URI (note: subdirectory requires "subdirectory=" prefix)
source = GitSource.from_uri(
    "git+https://github.com/org/repo@v1.0.0#subdirectory=src/module"
)

# Or construct directly
source = GitSource(
    url="https://github.com/org/repo",
    ref="v1.0.0",
    subdirectory="src/module"
)

# For module resolution: resolve to cached path
module_path = source.resolve()

# For collection installation: install to specific directory
await source.install_to(target_dir)

# Get full URI (useful for lock files)
full_uri = source.uri  # Returns: git+https://github.com/org/repo@v1.0.0#subdirectory=src/module

# Get commit SHA (useful for lock files and update tracking)
commit = source.commit_sha  # Returns: full 40-char commit SHA from GitHub
```

**Features**:
- Automatic caching via uv (caches to ~/.amplifier/module-cache/)
- Unique cache key per url+ref+subdirectory (prevents cache collisions)
- Supports branches, tags, commit SHAs
- Supports subdirectories within repos (uv installs FROM subdirectory TO target)
- Supports private repos (via git credentials)
- Automatic SHA retrieval from GitHub for update tracking
- Two APIs: `resolve()` for module resolution, `install_to()` for collection installation

**Subdirectory Note**: When `#subdirectory=path` is specified, uv installs content FROM that subdirectory TO the target directory directly (doesn't recreate subdirectory structure). This enables collection + module coexistence patterns where both live in same repo with different subdirectories.

#### PackageSource

Installed Python package:

```python
from amplifier_module_resolution import PackageSource

# By package name
source = PackageSource("amplifier-module-provider-anthropic")

# Resolve to installed package location
module_path = source.resolve()
```

**Use case**: Pre-installed modules, system packages, vendored modules.

**Note**: Uses importlib.metadata to locate installed packages. Raises ModuleResolutionError if package not found.

## API Reference

### Source Implementations

#### FileSource

```python
class FileSource:
    """Local file source for module loading."""

    def __init__(self, path: str | Path):
        """Initialize with local file path.

        Args:
            path: Absolute or relative path to module directory
                  Supports file:// URI format (removes prefix)
                  Relative paths resolved to absolute
        """

    def resolve(self) -> Path:
        """Resolve to filesystem path.

        Validates path exists, is a directory, and contains Python files.

        Returns:
            Absolute path to module directory (self.path)

        Raises:
            ModuleResolutionError: If path doesn't exist, not a directory, or no Python files
        """
```

#### GitSource

```python
class GitSource:
    """Git repository source via uv."""

    def __init__(
        self,
        url: str,
        ref: str = "main",
        subdirectory: str | None = None
    ):
        """Initialize with git repository details.

        Args:
            url: Git repository URL (https://github.com/org/repo)
            ref: Git ref (branch, tag, or commit SHA)
            subdirectory: Optional subdirectory within repo
        """

    @classmethod
    def from_uri(cls, uri: str) -> "GitSource":
        """Parse git+https://... URI format.

        Format: git+https://github.com/org/repo@ref#subdirectory=path

        Args:
            uri: Git URI string

        Returns:
            GitSource instance

        Example:
            >>> source = GitSource.from_uri(
            ...     "git+https://github.com/org/repo@v1.0.0#subdirectory=src/module"
            ... )
            >>> source.url == "https://github.com/org/repo"
            >>> source.ref == "v1.0.0"
            >>> source.subdirectory == "src/module"
        """

    def resolve(self) -> Path:
        """Resolve to cached git repository path.

        Downloads repo via uv to cache (~/.amplifier/module-cache/) if not cached.
        When subdirectory is specified, uv installs FROM subdirectory TO cache path.

        Cache key includes url+ref+subdirectory for unique isolation per module.

        Returns:
            Path to cached module directory

        Raises:
            InstallError: If git clone/download fails
        """

    async def install_to(self, target_dir: Path) -> None:
        """Install git repository to target directory.

        Used by collection installer (InstallSourceProtocol).
        Downloads repo directly to target_dir via uv pip install.

        Args:
            target_dir: Directory to install into (will be created)

        Raises:
            InstallError: If git installation fails
        """

    @property
    def uri(self) -> str:
        """Reconstruct full git+ URI in standard format.

        Returns:
            Full URI like: git+https://github.com/org/repo@ref#subdirectory=path

        Used by collection installer to store source URI in lock file.
        """
```

#### PackageSource

```python
class PackageSource:
    """Installed Python package source."""

    def __init__(self, package_name: str):
        """Initialize with package name.

        Args:
            package_name: Name of installed package
        """

    def resolve(self) -> Path:
        """Resolve to installed package path.

        Uses importlib.metadata to locate package.
        Returns the package root directory.

        Returns:
            Path to installed package

        Raises:
            ModuleResolutionError: If package not installed
        """
```

### Resolver Implementations

**→ See [Resolver Specification](docs/SPECIFICATION.md#reference-implementation-standardmodulesourceresolver) for complete contract.**

#### StandardModuleSourceResolver

```python
from amplifier_module_resolution import StandardModuleSourceResolver
from typing import Protocol

class SettingsProviderProtocol(Protocol):
    """Interface for settings access."""
    def get_module_sources(self) -> dict[str, str]:
        """Get module source overrides from settings."""

class StandardModuleSourceResolver:
    """Standard 5-layer resolution strategy.

    This is ONE implementation - apps can create alternatives.
    """

    def __init__(
        self,
        workspace_dir: Path | None = None,
        settings_provider: SettingsProviderProtocol | None = None
    ):
        """Initialize with app-specific configuration.

        Args:
            workspace_dir: Optional workspace convention path (layer 2)
            settings_provider: Optional settings provider (layer 3)
        """

    def resolve(
        self,
        module_id: str,
        profile_hint: str | None = None
    ) -> ModuleSource:
        """Resolve module ID to source using 6-layer strategy.

        Resolution order (first match wins):
        1. Environment: AMPLIFIER_MODULE_<ID>
        2. Workspace: workspace_dir/<id>/
        3. Settings provider: Merges project + user (project wins)
        4. Collection modules: Registered via installed collections
        5. Profile hint: profile_hint parameter
        6. Package: Find via importlib

        Args:
            module_id: Module identifier (e.g., "provider-anthropic")
            profile_hint: Optional source from profile module config

        Returns:
            ModuleSource instance (FileSource, GitSource, or PackageSource)

        Raises:
            ModuleNotFoundError: If module cannot be resolved

        Example:
            >>> resolver = StandardModuleSourceResolver(...)
            >>> source = resolver.resolve("provider-anthropic")
            >>> module_path = source.resolve()
        """

    def resolve_with_layer(
        self,
        module_id: str,
        profile_hint: str | None = None
    ) -> tuple[ModuleSource, str]:
        """Resolve and return which layer resolved it.

        Returns:
            Tuple of (source, layer_name) where layer_name is one of:
            "env", "workspace", "settings", "collection", "profile", "package"

        Useful for debugging and display.

        Example:
            >>> source, layer = resolver.resolve_with_layer("provider-anthropic")
            >>> print(f"Resolved from: {layer}")
            Resolved from: settings
        """
```

---

## Usage Examples

### CLI Application

```python
from amplifier_module_resolution import StandardModuleSourceResolver
from amplifier_config import ConfigManager
from pathlib import Path

# Set up settings provider
config = ConfigManager(paths=ConfigPaths(...))

# Create resolver with CLI configuration
resolver = StandardModuleSourceResolver(
    workspace_dir=Path(".amplifier/modules"),
    settings_provider=config,
)

# Resolve module to source
source = resolver.resolve("provider-anthropic")

# Resolve to module path
module_path = source.resolve()

# Load module (amplifier-core handles this)
from amplifier_core import load_module
provider = load_module(module_path, "provider-anthropic")
```

### Web Application (Custom Resolver)

```python
from amplifier_core.module_sources import ModuleSource, ModuleSourceResolver
import httpx
import zipfile

class HttpZipSource:
    """Web-specific: HTTP zip downloads."""

    def __init__(self, url: str):
        self.url = url

    async def install(self, target_dir: Path) -> Path:
        """Download and extract zip to target."""
        async with httpx.AsyncClient() as client:
            response = await client.get(self.url)
            response.raise_for_status()

            # Extract zip
            temp_zip = target_dir.parent / "temp.zip"
            temp_zip.write_bytes(response.content)

            with zipfile.ZipFile(temp_zip) as zf:
                zf.extractall(target_dir)

            temp_zip.unlink()
            return target_dir

class WebModuleResolver:
    """Web-specific: 2-layer resolution (database → registry)."""

    def __init__(self, registry_url: str, database):
        self.registry_url = registry_url
        self.db = database

    async def resolve(self, module_id: str, profile_hint=None) -> ModuleSource:
        """Resolve using web-specific strategy."""

        # Layer 1: Check database for workspace-specific override
        override = await self.db.get_module_override(module_id)
        if override:
            return HttpZipSource(override.url)

        # Layer 2: Query web registry
        url = f"{self.registry_url}/modules/{module_id}/latest.zip"
        return HttpZipSource(url)

# Use in web service
resolver = WebModuleResolver(
    registry_url="https://modules.amplifier.dev",
    database=db
)

source = await resolver.resolve("provider-anthropic")
module_path = await source.install(workspace_cache_dir)
```

### Enterprise Application (Corporate Artifact Server)

```python
class EnterpriseModuleResolver:
    """Corporate artifact server resolution."""

    def __init__(self, artifact_server: str, auth_token: str):
        self.server = artifact_server
        self.token = auth_token

    async def resolve(self, module_id: str, profile_hint=None) -> ModuleSource:
        """Resolve from corporate artifact server.

        No git, no internet - only corporate server.
        """
        import httpx

        # Query corporate registry
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.server}/api/modules/{module_id}",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            response.raise_for_status()
            module_info = response.json()

        # Return source pointing to corporate mirror
        return HttpZipSource(module_info["download_url"])

# Use in enterprise environment
resolver = EnterpriseModuleResolver(
    artifact_server="https://artifacts.corp.example.com",
    auth_token=get_corp_token()
)
```

### Testing (Mock Sources)

```python
from amplifier_module_resolution import FileSource
from pathlib import Path
import tempfile

def test_module_resolution():
    """Test module resolution with file source."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create mock module
        module_src = tmp_path / "mock-module"
        module_src.mkdir()
        (module_src / "__init__.py").write_text("# Mock module")

        # Create file source
        source = FileSource(module_src)

        # Resolve to module path
        module_path = source.resolve()

        # Verify resolution
        assert module_path == module_src.resolve()
        assert (module_path / "__init__.py").exists()
```

---

## Resolution Strategy

**→ See [Resolution Strategy Specification](docs/SPECIFICATION.md#resolution-order-5-layers) for complete technical details.**

The StandardModuleSourceResolver uses a 5-layer fallback: env → workspace → settings → profile → package.

### Custom Resolution Strategies

Apps can implement custom resolvers for different environments.

**→ See [Alternative Implementations](docs/SPECIFICATION.md#alternative-implementations) for complete examples.**

---

## API Reference

**→ See [Technical Specification](docs/SPECIFICATION.md) for complete protocol and contract details.**

---

## Error Handling

**→ See [Error Handling Specification](docs/SPECIFICATION.md#error-handling) for complete error handling contracts.**

The library raises `ModuleResolutionError` with detailed context for troubleshooting.

---

## Design Philosophy

**→ See [Technical Specification](docs/SPECIFICATION.md) for complete design rationale** including:
- Why this is a library, not kernel
- Why 5 layers
- Alternative implementation strategies


---

## Dependencies

**Runtime**: Python >=3.11, uv (for GitSource)
**Development**: pytest, pytest-asyncio

**→ See [Technical Specification](docs/SPECIFICATION.md#dependencies) for complete dependency details.**

---

## Testing

```bash
# Run tests
uv sync --dev && pytest

# With coverage
pytest --cov=amplifier_module_resolution --cov-report=html
```

**→ See [Technical Specification](docs/SPECIFICATION.md) for complete details** on:
- Test coverage and strategy
- When to use this library vs custom resolvers
- Philosophy compliance
- Future considerations and kernel promotion criteria

---

## Contributing

This project welcomes contributions and suggestions. Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

---

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
