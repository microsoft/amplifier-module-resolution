# amplifier-module-resolution

**Module source resolution with pluggable strategies for Amplifier applications**

amplifier-module-resolution provides standard implementations of amplifier-core's ModuleSource and ModuleSourceResolver protocols. It implements a 5-layer resolution strategy using uv for git operations, supports file/git/package sources, and integrates with settings-based overrides.

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

**Resolution order** (first match wins):

1. **Environment variable**: `AMPLIFIER_MODULE_<ID>=<source>`
2. **Workspace convention**: `.amplifier/modules/<id>/`
3. **Settings provider**: Merges project + user settings (project takes precedence)
4. **Profile hint**: Source specified in profile module config
5. **Installed package**: `amplifier-module-<id>` or `<id>` package

**Note**: The settings provider (layer 3) internally merges project and user settings, with project taking precedence. From the API perspective, this is a single layer that consolidates multiple configuration sources.

**Example resolution**:

```bash
# Layer 1: Environment override (highest precedence)
export AMPLIFIER_MODULE_PROVIDER_ANTHROPIC="file:///home/dev/custom-provider"

# Layer 2: Workspace convention
mkdir -p .amplifier/modules/provider-anthropic
# Put development code here

# Layer 3: Settings provider (merges project + user, project wins)
# .amplifier/settings.yaml (project - higher precedence)
sources:
  provider-anthropic: git+https://github.com/team/custom-provider@main

# ~/.amplifier/settings.yaml (user - lower precedence)
sources:
  provider-anthropic: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main

# Layer 4: Profile hint
# In profile.md
providers:
  - module: provider-anthropic
    source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main

# Layer 5: Installed package (lowest precedence)
uv pip install amplifier-module-provider-anthropic
```

**Result**: Layer 1 (env) wins if set, otherwise layer 2, etc.

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
```

**Features**:
- Automatic caching via uv (caches to ~/.amplifier/module-cache/)
- Supports branches, tags, commit SHAs
- Supports subdirectories within repos
- Supports private repos (via git credentials)
- Two APIs: `resolve()` for module resolution, `install_to()` for collection installation

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
        Returns path to cached module (including subdirectory if specified).

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
        """Resolve module ID to source using 5-layer strategy.

        Resolution order (first match wins):
        1. Environment: AMPLIFIER_MODULE_<ID>
        2. Workspace: workspace_dir/<id>/
        3. Settings provider: Merges project + user (project wins)
        4. Profile hint: profile_hint parameter
        5. Package: Find via importlib

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
            "env", "workspace", "settings", "profile", "package"

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

## Resolution Strategies Explained

### The 5-Layer Strategy (StandardModuleSourceResolver)

```python
# Layer 1: Environment variable (developer override)
# Terminal: export AMPLIFIER_MODULE_PROVIDER_ANTHROPIC="file:///dev/custom"
# Code checks: os.environ.get(f"AMPLIFIER_MODULE_{module_id.upper().replace('-', '_')}")

# Layer 2: Workspace convention (local development)
# Check: {workspace_dir}/{module_id}/
# Example: .amplifier/modules/provider-anthropic/

# Layer 3: Settings provider (merges project + user settings)
# From: settings_provider.get_module_sources()
# Internally: .amplifier/settings.yaml (project) overrides ~/.amplifier/settings.yaml (user)
# Via: One API call that returns merged dict

# Layer 4: Profile hint (profile-specified source)
# From: profile module config -> source field
# Example: providers[0].source

# Layer 5: Installed package (system fallback)
# Check: importlib.metadata.distribution(f"amplifier-module-{module_id}")
# Or: importlib.metadata.distribution(module_id)
```

**Design principle**: Higher layers override lower layers, enabling development workflow:
1. Develop locally (layer 2: workspace)
2. Test with team (layer 3: settings provider)
3. Deploy with stable (layer 4: profile default)

### Alternative: 2-Layer Strategy (Simple)

Custom resolvers can use simpler strategies:

```python
class SimpleResolver:
    """2-layer: settings → profile hint (no workspace, no fallback)."""

    def __init__(self, settings_provider):
        self.settings = settings_provider

    def resolve(self, module_id: str, profile_hint=None) -> ModuleSource:
        # Layer 1: Settings override
        sources = self.settings.get_module_sources()
        if module_id in sources:
            return GitSource.from_uri(sources[module_id])

        # Layer 2: Profile hint (required)
        if not profile_hint:
            raise ModuleResolutionError(
                f"Module source not specified: {module_id}",
                context={"message": "Specify source in settings or profile"}
            )

        return GitSource.from_uri(profile_hint)
```

**When to use**: Simpler applications where profiles always specify sources.

**Alternative with injectable fallback** (if app wants defaults):

```python
class ResolverWithFallback:
    """App provides its own fallback registry (policy injection)."""

    def __init__(self, settings_provider, app_defaults: dict[str, str]):
        self.settings = settings_provider
        self.app_defaults = app_defaults  # App policy, not library policy

    def resolve(self, module_id: str, profile_hint=None) -> ModuleSource:
        # Layer 1: Settings
        sources = self.settings.get_module_sources()
        if module_id in sources:
            return GitSource.from_uri(sources[module_id])

        # Layer 2: Profile hint
        if profile_hint:
            return GitSource.from_uri(profile_hint)

        # Layer 3: App-provided defaults (injected)
        if module_id in self.app_defaults:
            return GitSource.from_uri(self.app_defaults[module_id])

        raise ModuleResolutionError(f"Module source not found: {module_id}")

# CLI app usage
cli_defaults = {
    "provider-anthropic": "git+https://github.com/microsoft/amplifier-module-provider-anthropic@main",
    # CLI's opinionated defaults
}
resolver = ResolverWithFallback(settings, app_defaults=cli_defaults)
```

**When to use**: Apps that want to provide defaults without hardcoding them in the library.

### Alternative: Database-First Strategy (Web)

```python
class DatabaseResolver:
    """Web-specific: database → HTTP registry."""

    async def resolve(self, module_id: str, profile_hint=None) -> ModuleSource:
        # Layer 1: Workspace-specific override in database
        override = await self.db.get_module_override(workspace_id, module_id)
        if override:
            return DatabaseBlobSource(override.blob)

        # Layer 2: HTTP registry
        url = f"{self.registry}/modules/{module_id}/latest.zip"
        return HttpZipSource(url)
```

**When to use**: Web applications with centralized module storage.

---

## API Reference

### Protocols

```python
from typing import Protocol

class SettingsProviderProtocol(Protocol):
    """Interface for settings access.

    Apps provide implementation matching their settings system.
    """

    def get_module_sources(self) -> dict[str, str]:
        """Get module source overrides from settings.

        Returns:
            Dict mapping module_id -> source_uri
        """
```

**Standard implementation**: amplifier-config's ConfigManager implements this protocol.

---

## Error Handling

### Exceptions

```python
from amplifier_module_resolution import ModuleResolutionError, InstallError

# Resolution errors
class ModuleResolutionError(Exception):
    """Module resolution failed."""
    def __init__(self, message: str, context: dict | None = None):
        self.message = message
        self.context = context or {}

# Installation errors
class InstallError(ModuleResolutionError):
    """Module installation failed."""

# Usage
try:
    source = resolver.resolve("unknown-module")
except ModuleResolutionError as e:
    print(f"Error: {e.message}")
    print(f"Searched layers: {e.context.get('searched_layers')}")
```

### Subprocess Error Handling

Git operations use subprocess with clear error reporting:

```python
try:
    # uv pip install ...
    result = subprocess.run([...], check=True, capture_output=True)
except subprocess.CalledProcessError as e:
    raise InstallError(
        f"Git installation failed: {e.stderr.decode()}",
        context={
            "command": e.cmd,
            "returncode": e.returncode,
            "stdout": e.stdout.decode(),
            "stderr": e.stderr.decode()
        }
    )
```

**Philosophy**: Fail fast with actionable error messages, not silent failures.

---

## Design Philosophy

### Why Library, Not Kernel?

**Question**: Should module resolution be in amplifier-core (kernel)?

**Kernel philosophy litmus test**: "Could two teams want different behavior?"

**Answer**: **YES** - Resolution strategy varies significantly:

**Resolution order differs**:
- CLI: env → workspace → settings → profile → package
- Web: database → registry → cache
- Enterprise: corporate server → local mirror → fail
- Air-gapped: cache only → fail

**Source types differ**:
- CLI: git (uv), file (shutil), package (importlib)
- Web: HTTP zip, database blob, S3 bucket
- Enterprise: Artifact server API
- Air-gapped: File copy only

**Conclusion**: Module resolution is **policy** (varies by app) → **library** (not kernel).

**Two-implementation rule**: Only 1 implementation exists (CLI). Need ≥2 before kernel promotion.

**Future**: After web UI + 1-2 more apps, revisit for kernel promotion if patterns converge.

### Why uv Specifically?

**Question**: Why use uv for git operations?

**Answer**: StandardModuleSourceResolver is the **CLI policy** implementation.

Different resolvers use different tools:
- StandardModuleSourceResolver: uv (CLI choice)
- WebModuleResolver: httpx (web choice)
- EnterpriseResolver: Corporate API client
- CustomResolver: Your choice

**This library provides ONE implementation, not THE ONLY implementation.**

Apps can create custom resolvers without depending on this library at all - just implement the kernel protocols.

### Why 5 Layers?

**Question**: Why so many resolution layers?

**Answer**: Supports complete development workflow:

```python
# Development: Use local workspace copy
.amplifier/modules/provider-anthropic/  # Layer 2

# Testing: Override in settings (project settings win over user settings)
# .amplifier/settings.yaml
sources:
  provider-anthropic: git+https://github.com/team/fork@test-branch  # Layer 3

# Production: Use stable profile default
# profile.md
providers:
  - module: provider-anthropic
    source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@v1.0.0  # Layer 4

# Quick test: Environment variable
export AMPLIFIER_MODULE_PROVIDER_ANTHROPIC="file:///tmp/test-provider"  # Layer 1 (highest)
```

**Each layer serves a purpose**. Apps with simpler needs can use simpler resolvers.

---

## Alternative Implementations

### Example: HTTP-Only Resolver

```python
import httpx
import zipfile

class HttpZipSource:
    """HTTP zip download source."""

    def __init__(self, url: str):
        self.url = url

    async def install(self, target_dir: Path) -> Path:
        async with httpx.AsyncClient() as client:
            response = await client.get(self.url)
            response.raise_for_status()

            temp_zip = target_dir.parent / f"{target_dir.name}.zip"
            temp_zip.write_bytes(response.content)

            with zipfile.ZipFile(temp_zip) as zf:
                zf.extractall(target_dir)

            temp_zip.unlink()
            return target_dir

class HttpOnlyResolver:
    """Simple HTTP-only resolver (no git, no uv)."""

    def __init__(self, registry_url: str):
        self.registry_url = registry_url

    def resolve(self, module_id: str, profile_hint=None) -> ModuleSource:
        """Single-layer resolution: HTTP registry only."""
        url = f"{self.registry_url}/modules/{module_id}/latest.zip"
        return HttpZipSource(url)

# Use without amplifier-module-resolution library
resolver = HttpOnlyResolver("https://modules.example.com")
source = resolver.resolve("provider-anthropic")
```

**When to use**: Web applications, serverless environments, contexts without git/uv.

### Example: Air-Gapped Resolver

```python
class LocalMirrorSource:
    """File copy from local mirror."""

    def __init__(self, mirror_path: Path):
        self.mirror_path = mirror_path

    async def install(self, target_dir: Path) -> Path:
        import shutil
        shutil.copytree(self.mirror_path, target_dir)
        return target_dir

class AirGappedResolver:
    """Air-gapped: local cache only."""

    def __init__(self, cache_dir: Path):
        self.cache = cache_dir

    def resolve(self, module_id: str, profile_hint=None) -> ModuleSource:
        """Resolve from local mirror only."""
        mirror_path = self.cache / module_id

        if not mirror_path.exists():
            raise ModuleResolutionError(
                f"Module not in local cache: {module_id}",
                context={"cache_dir": self.cache}
            )

        return LocalMirrorSource(mirror_path)

# Use in air-gapped deployment
resolver = AirGappedResolver(cache_dir=Path("/opt/amplifier/modules"))
```

**When to use**: High-security environments, offline deployments.

---

## Dependencies

### Runtime

**Required**:
- Python >=3.11 (stdlib: subprocess, importlib, pathlib, os)

**External tools** (for StandardModuleSourceResolver only):
- **uv** (for GitSource) - Not required if using custom resolver

**Optional** (via protocols):
- Settings provider (for settings-based overrides)

### Development

- pytest >=8.0
- pytest-asyncio (async testing)

**Note**: This library implements amplifier-core protocols (ModuleSource, ModuleSourceResolver) and uses protocol-based integration for settings access.

---

## Testing

### Running Tests

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Or using uv sync
uv sync --dev

# Run tests
pytest

# Run with coverage
pytest --cov=amplifier_module_resolution --cov-report=html
```

### Test Coverage

The library includes comprehensive tests:

- **Unit tests**: URI parsing, source type detection, resolution layer logic
- **Integration tests**: FileSource with real directories, GitSource with mock subprocess
- **Protocol tests**: StandardModuleSourceResolver implements kernel protocol
- **Edge cases**: Missing modules, invalid URIs, subprocess failures

Target coverage: >90%

**Note**: Git operations use mock subprocess (no actual git calls in tests).

---

## Design Decisions

### Why Protocol-Based Source Interface?

**Alternative**: Hardcode file, git, package types

**Problem**: Can't add new source types without library changes

**Solution**: Any object implementing `ModuleSource` protocol works

**Benefit**: Apps create custom sources (HTTP, database, artifact server) without modifying library.

### Why Include Alternative Examples?

**Rationale**: This library is **one policy implementation**, not **the only implementation**.

By including HttpZipResolver, DatabaseResolver, and AirGappedResolver examples, we demonstrate:
- How to create custom resolvers
- When to use this library vs custom implementation
- That kernel protocols support diverse strategies

**Message**: "Use this library if it fits; create custom resolver if it doesn't."

---

## When to Use This Library

### Use StandardModuleSourceResolver When:

✅ Building desktop/CLI applications using filesystem
✅ Supporting local development (workspace convention)
✅ Using settings files for source overrides
✅ Need standard git+file+package source support
✅ Have uv available for git operations

### Create Custom Resolver When:

✅ Building web applications with database storage
✅ Need HTTP-only downloads (no git/uv)
✅ Corporate environment with artifact server
✅ Air-gapped deployment (local mirrors only)
✅ Different resolution precedence needed
✅ Custom source types required

**The library enables, not restricts**. Custom resolvers are expected and encouraged.

---

## Philosophy Compliance

### Kernel Philosophy ✅

**"Mechanism, not policy"**:
- ⚠️ **This library IS policy** - resolution strategy, source types, layer order
- ✅ **Correctly placed in library** (not kernel)
- ✅ Apps can swap strategies (create custom resolvers)

**"Two-implementation rule"**:
- ✅ Respects rule - stays in library until convergence proven
- ✅ After web UI + 1-2 more apps, revisit for kernel promotion
- ✅ Evidence-driven kernel additions, not speculation

**"Don't break modules"**:
- ✅ Protocol interface ensures backward compatibility
- ✅ Concrete implementations can change without breaking apps

**"Prefer saying no to keep center still"**:
- ✅ Kernel says "no" to resolution implementations
- ✅ Kernel provides protocols only
- ✅ Edges (this library) provide policy implementations

### Ruthless Simplicity ✅

**No caching beyond uv's built-in**:
- YAGNI - uv already caches git clones
- Add explicit caching if proven needed

**No retry logic**:
- Fail fast on errors
- Apps can implement retry if needed

**No complex source type detection**:
- Simple prefix checking (git+, file://, package name)
- Clear and predictable

**No validation beyond existence checks**:
- Modules validate themselves on load
- Not resolver's responsibility

---

## Future Considerations

### Kernel Promotion Criteria

**After web UI + 1-2 other apps exist**, evaluate for kernel promotion:

**Questions**:
1. Do all apps use similar resolution patterns? (If >80% similar → extract common core)
2. Do all apps use same source types? (If yes → promote to kernel)
3. Is there a minimal common core? (FileSource is likely universal)
4. Does kernel benefit outweigh stability cost? (Weigh carefully)

**Likely outcome**:
- FileSource might move to kernel (universal, no external dependencies)
- Rest stays in library (policy varies: git vs HTTP vs database)

**Current decision**: Stay in library. Revisit with evidence from multiple implementations.

### Potential Additions (Only If Proven Needed)

**HTTP zip source**:
- **Add when**: Multiple apps request HTTP installation
- **Add how**: Add HttpZipSource alongside File/Git/Package

**Caching layer**:
- **Add when**: Performance profiling shows installation bottleneck
- **Add how**: Cache with TTL and invalidation

**Parallel installation**:
- **Add when**: Apps request faster bulk installation
- **Add how**: asyncio.gather with semaphore

**Offline mode**:
- **Add when**: Apps request offline support
- **Add how**: Network detection + cache-first resolution

**Current approach**: YAGNI - ship minimal, grow based on evidence.

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
