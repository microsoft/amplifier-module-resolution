---
last_updated: 2025-10-16
status: stable
audience: developer
---

# Module Source Specification (Reference Implementation)

**Reference implementation specification for module source resolution.**

This document describes the **StandardModuleSourceResolver** and app-layer conventions shipped with Amplifier. For kernel contracts, see [amplifier-core MODULE_SOURCE_PROTOCOL.md](https://github.com/microsoft/amplifier-core/blob/main/docs/MODULE_SOURCE_PROTOCOL.md).

For usage guides, see:
- [USER_GUIDE.md](./USER_GUIDE.md) - User guide for customizing module sources

---

## Overview

### Purpose

The reference implementation provides a **5-layer module resolution strategy** supporting:
- Local development workflows
- Git-based remote modules
- Workspace conventions
- YAML configuration files
- Community module ecosystem

### Architecture: Kernel + Reference Policy

Following Amplifier's kernel philosophy (mechanism not policy):
- **Mechanism in kernel**: Module loading/mounting, protocol definitions
- **Policy in reference impl**: StandardModuleSourceResolver with 6-layer fallback
- **Convention over configuration**: Workspace convention is optional
- **Text-first**: YAML configs, string URIs, readable logs
- **Non-interference**: Failures degrade gracefully to next layer

**Kernel contracts:** [amplifier-core MODULE_SOURCE_PROTOCOL.md](https://github.com/microsoft/amplifier-core/blob/main/docs/MODULE_SOURCE_PROTOCOL.md)

---

## Resolution Architecture

### Reference Implementation: StandardModuleSourceResolver

**This is app-layer policy, not kernel.**

The kernel provides protocols ([MODULE_SOURCE_PROTOCOL.md](https://github.com/microsoft/amplifier-core/blob/main/docs/MODULE_SOURCE_PROTOCOL.md)). This document describes the **reference implementation** provided by this library.

**Architecture:**

1. **StandardModuleSourceResolver** - Reference policy (app-layer)
   - WHERE to find modules (5-layer fallback)
   - Can be swapped for custom strategies
   - Covers 99% of use cases

2. **AmplifierModuleLoader** - Kernel mechanism
   - HOW to mount modules
   - Universal, stable
   - Injects resolver via mount point

```python
# App layer provides resolver (policy)
coordinator.mount("module-source-resolver", StandardModuleSourceResolver())

# Kernel loader uses injected resolver (mechanism)
loader = AmplifierModuleLoader(coordinator)
```

### Resolution Order (5 Layers)

StandardModuleSourceResolver checks 5 layers, first match wins:

```
┌──────────────────────────────────────────────────────────┐
│ 1. ENVIRONMENT VARIABLE (highest precedence)             │
│    AMPLIFIER_MODULE_<MODULE_ID>=<source-uri>             │
│    → Temporary overrides, debugging, CI/CD               │
├──────────────────────────────────────────────────────────┤
│ 2. WORKSPACE CONVENTION                                   │
│    .amplifier/modules/<module-id>/                       │
│    → Local development, active module work               │
├──────────────────────────────────────────────────────────┤
│ 3. SETTINGS PROVIDER (merges project + user)             │
│    .amplifier/settings.yaml (project wins)               │
│    ~/.amplifier/settings.yaml (user fallback)            │
│    → Project-wide or user-global overrides               │
├──────────────────────────────────────────────────────────┤
│ 4. PROFILE HINT                                           │
│    profile.tools[].source field                          │
│    → Profile-specified default sources                   │
├──────────────────────────────────────────────────────────┤
│ 5. INSTALLED PACKAGE (lowest precedence)                 │
│    importlib.metadata lookup                             │
│    → Pre-installed standard modules, fallback            │
└──────────────────────────────────────────────────────────┘

First match wins - resolution stops at first successful layer.
```

**Note**: The settings provider (layer 3) internally merges project settings (`.amplifier/settings.yaml`) and user settings (`~/.amplifier/settings.yaml`), with project taking precedence. From the resolver's API perspective, this is a single layer.

### Resolution Algorithm (Contract)

**Pseudocode defining required behavior:**

```python
def resolve(module_id: str, profile_source: str | dict | None = None) -> ModuleSource:
    """
    Resolve module source through layered fallback.

    Args:
        module_id: Module identifier (e.g., "tool-bash")
        profile_source: Optional source from profile (string URI or object)

    Returns:
        ModuleSource object with resolved path/URL

    Raises:
        ModuleNotFoundError: If all layers fail
    """

    # Layer 1: Environment variable
    env_key = f"AMPLIFIER_MODULE_{module_id.upper().replace('-', '_')}"
    if env_value := os.getenv(env_key):
        return parse_source(env_value)

    # Layer 2: Workspace convention
    if workspace_source := check_workspace(module_id):
        return workspace_source

    # Layer 3: Settings provider (merges project + user, project wins)
    if settings_provider:
        sources = settings_provider.get_module_sources()
        if module_id in sources:
            return parse_source(sources[module_id])

    # Layer 4: Collection modules (registered via installed collections)
    if collection_provider:
        collection_modules = collection_provider.get_collection_modules()
        if module_id in collection_modules:
            return FileSource(collection_modules[module_id])

    # Layer 5: Profile source
    if profile_source:
        return parse_source(profile_source)

    # Layer 6: Installed package
    return resolve_package(module_id)
```

**Actual implementation**: See `src/amplifier_module_resolution/resolvers.py:52-92`

---

## Source Field Schema

### Design: MCP-Aligned Hybrid

**Supports both string and object formats** (inspired by Model Context Protocol).

**String format** (simple, recommended):
```yaml
source: git+https://github.com/org/repo@ref
source: file:///path/to/module
```

**Object format** (advanced, extensible):
```yaml
source:
  type: git
  url: https://github.com/org/repo
  ref: main
  subdirectory: packages/tool
```

### String Format (Recommended)

**URI schemes:**

```yaml
# Git with branch
source: git+https://github.com/org/repo@main

# Git with tag
source: git+https://github.com/org/repo@v1.0.0

# Git with subdirectory
source: git+https://github.com/org/monorepo@main#subdirectory=packages/tool

# Local absolute path
source: file:///absolute/path/to/module

# Local relative path
source: ./relative/path

# Package name (fallback)
source: my-package-name
```

### Object Format (Advanced)

**Schema:**

```yaml
source:
  type: git | file | package    # Required

  # For type: git
  url: string                   # Required
  ref: string                   # Optional (default: main)
  subdirectory: string          # Optional

  # For type: file
  path: string                  # Required

  # For type: package
  name: string                  # Required
```

**Examples:**

```yaml
# Git source
source:
  type: git
  url: https://github.com/microsoft/amplifier-module-tool-bash
  ref: v1.2.0

# File source
source:
  type: file
  path: /home/user/dev/tool-bash

# Package source
source:
  type: package
  name: amplifier-module-tool-bash
```

### Why Both?

- **String**: Concise for 95% of cases
- **Object**: Structured for tooling, extensible for future fields (env, timeout, config)
- **Future-proof**: Can add MCP-like fields later (environment, timeout, etc.)

---

## Source Types

### FileSource

**Contract:** Resolves to local filesystem path.

**Accepts:**
- `file:///absolute/path`
- `/absolute/path`
- `./relative/path`
- `../parent/path`

**Behavior:**
- Path resolved relative to working directory
- Must exist and be valid module directory
- No caching (always uses current state)

**Validation:**
- Path exists
- Path is directory
- Directory contains Python module (has `*.py` files)

### GitSource

**Contract:** Resolves to cached git repository.

**Accepts:**
- `git+https://github.com/org/repo@ref`
- `git+ssh://git@github.com/org/repo@ref`
- `git+https://github.com/org/repo@ref#subdirectory=path`

**Behavior:**
- Downloads to `~/.amplifier/module-cache/<hash>/<ref>/`
- Cache key: `hash(url + ref + subdirectory)` - ensures unique cache per module
- Cache checked before download
- Uses `uv pip install --target` for download

**Subdirectory Handling:**

When `#subdirectory=path` is specified, `uv` installs content **FROM** subdirectory **TO** target directory directly. The subdirectory structure is **not** recreated at the target.

Example:
```bash
# Command
uv pip install --target ~/.amplifier/module-cache/abc123/main \
  "git+https://github.com/org/repo@main#subdirectory=modules/tool-x"

# Content installed at: ~/.amplifier/module-cache/abc123/main/
# NOT at:              ~/.amplifier/module-cache/abc123/main/modules/tool-x/
```

This enables collection + module coexistence patterns where both live in the same repository:
```yaml
# Collection root
source: git+https://github.com/org/collection@main

# Module from same repo, different subdirectory
source: git+https://github.com/org/collection@main#subdirectory=modules/tool-x
```

Each gets a unique cache key and cache directory, preventing overwrites.

**Caching:**
- Location: `~/.amplifier/module-cache/`
- Invalidation: Manual (`amplifier module refresh`)
- Concurrent access: Safe (atomic writes)

**Authentication:**
- HTTPS: Git credential helper
- SSH: SSH keys (~/.ssh/)

### PackageSource

**Contract:** Resolves to installed Python package.

**Fallback order:**
1. Try exact module ID as package name
2. Try `amplifier-module-<module-id>` convention
3. Fail with helpful error

**Discovery:**
- Uses Python entry points: `amplifier.modules`
- Standard `importlib.metadata` lookup

---

## Configuration Formats

### YAML Configuration Files

**File locations:**
- Project: `.amplifier/settings.yaml` (commit to git)
- User: `~/.amplifier/settings.yaml` (personal)

**Schema:**

```yaml
sources:
  <module-id>: <source-uri-or-object>
```

**Examples:**

```yaml
sources:
  tool-bash: file:///home/user/dev/tool-bash
  tool-web: git+https://github.com/microsoft/amplifier-module-tool-web@v1.0.0
  tool-custom:
    type: git
    url: https://github.com/org/custom-tool
    ref: feature-branch
```

### Profile YAML

**Profiles specify default sources:**

```yaml
tools:
  - module: tool-bash
    source: git+https://github.com/microsoft/amplifier-module-tool-bash@main

  - module: tool-custom
    source:
      type: git
      url: https://github.com/you/custom-tool
      ref: v1.0.0
```

**If no `source` field:** Uses resolution layers (workspace → config → package).

### Environment Variables

**Format:** `AMPLIFIER_MODULE_<MODULE_ID_UPPERCASE>=<source-uri>`

**Examples:**
```bash
export AMPLIFIER_MODULE_TOOL_BASH=/home/user/dev/tool-bash
export AMPLIFIER_MODULE_PROVIDER_ANTHROPIC=git+https://github.com/fork/anthropic@feature
export AMPLIFIER_MODULE_CUSTOM_ANALYZER=file:///home/user/projects/analyzer
```

**Naming rules:**
- Uppercase module ID
- Replace hyphens with underscores
- Prefix with `AMPLIFIER_MODULE_`

---

## Workspace Convention

### Directory Structure

```
.amplifier/
└── modules/
    ├── tool-bash/              # Module directory
    ├── tool-filesystem/        # Module directory
    └── provider-anthropic/     # Module directory
```

**Why `.amplifier/modules/` (not `modules/`):**
- Consistency: All Amplifier state in `.amplifier/`
- Gitignore: Already excluded
- Clear ownership: Amplifier-managed directory
- Commands abstract location: `amplifier module dev <cmd>` handles paths

**LLM access:** Session context includes workspace module list to help LLM tools.

### Discovery Contract

**Pseudocode:**

```python
def check_workspace(module_id: str) -> FileSource | None:
    """Check workspace convention for module."""
    path = Path(".amplifier/modules") / module_id

    if not path.exists():
        return None

    if is_empty_submodule(path):
        return None  # Uninitialized, fall through

    if is_valid_module(path):
        return FileSource(path)

    return None  # Invalid, fall through

def is_valid_module(path: Path) -> bool:
    """Directory contains Python module."""
    return any(path.glob("**/*.py"))

def is_empty_submodule(path: Path) -> bool:
    """Directory is uninitialized git submodule."""
    return (path / ".git").exists() and not any(path.glob("**/*.py"))
```

**Actual implementation**: See `src/amplifier_module_resolution/resolvers.py:132-172`

---

## Module Identity

### Module ID vs Package Name

**Module ID:**
- Primary identifier
- Used in profiles, configs, env vars
- Mount point name in coordinator
- Examples: `tool-bash`, `provider-anthropic`, `awesome-analyzer`

**Package Name:**
- Python package name (can be anything)
- Discovered via entry points
- Not referenced by users
- Examples: `amplifier-module-tool-bash`, `awesome-bash-tools`, `custom-pkg`

**Relationship:**

```yaml
# Profile specifies module ID and source
tools:
  - module: bash              # ID (mount point name)
    source: git+https://github.com/microsoft/amplifier-module-tool-bash

  - module: awesome-bash      # Different ID
    source: git+https://github.com/community/awesome-bash-tools
```

**Entry point must match module ID:**

```toml
# In package pyproject.toml (any package name)
[project]
name = "awesome-bash-tools"  # Package name (not used by Amplifier)

[project.entry-points."amplifier.modules"]
bash = "awesome_bash_tools"  # ID = "bash", points to package code
```

**Package name fallback (Layer 6):**

```python
def resolve_package(module_id: str) -> PackageSource:
    """Try to find installed package by module ID."""

    # Try exact ID as package name
    if package_exists(module_id):
        return PackageSource(module_id)

    # Try our naming convention
    convention = f"amplifier-module-{module_id}"
    if package_exists(convention):
        return PackageSource(convention)

    raise ModuleNotFoundError(...)
```

---

## Observability

### Logging Events

**Module resolution:**
```
[module:resolve] tool-bash -> env var (file:///home/user/dev/tool-bash)
[module:resolve] tool-filesystem -> workspace (.amplifier/modules/tool-filesystem)
[module:resolve] tool-web -> profile (git+...@main)
[module:resolve] provider-anthropic -> package (amplifier-module-provider-anthropic v1.0.0)
```

**Git caching:**
```
[module:cache:check] tool-web@main -> not found
[module:cache:download] Downloading git+https://github.com/.../tool-web@main
[module:cache:complete] Cached at ~/.amplifier/module-cache/abc123/main
[module:cache:check] tool-web@main -> found (abc123/main)
```

**Module mounting:**
```
[module:mount] tool-bash from file:///home/user/dev/tool-bash
[module:mount] tool-filesystem from workspace
[module:mount] tool-web from cache (abc123/main)
```

### CLI Observability

**amplifier module status:**

See [USER_GUIDE.md](./USER_GUIDE.md) for CLI command examples and output formats.

**amplifier profile show:**

Includes module source resolution for profile context.

---

## Error Handling

### Resolution Failures

**Behavior:**
- Try next layer on failure
- Log failure reason (debug level)
- If all layers fail, raise `ModuleNotFoundError` with comprehensive diagnostic

**Error message contract:**

```
Error: Module 'tool-custom' not found

Resolution attempted:
  1. Environment: AMPLIFIER_MODULE_TOOL_CUSTOM (not set)
  2. Workspace: .amplifier/modules/tool-custom (not found)
  3. Project: .amplifier/settings.yaml (no entry)
  4. User: ~/.amplifier/settings.yaml (no entry)
  5. Profile: (no source specified)
  6. Package: Tried 'tool-custom' and 'amplifier-module-tool-custom' (neither installed)

Suggestions:
  - Add source to profile: source: git+https://...
  - Install package: uv pip install <package-name>
  - Link local version: amplifier module link tool-custom /path
```

### Git Download Failures

**Graceful degradation:**

```python
try:
    return git_source.resolve()
except GitCloneError as e:
    logger.warning(f"Git download failed: {e}")
    # Fall through to next layer (don't raise)
    return None
```

If package installed, uses it as fallback.

---

## Module Structure Contract

### Required Files

```
<package-name>/
├── <package-code>/
│   └── __init__.py              # Required: Module entry point
├── pyproject.toml               # Required: Package metadata + entry points
└── README.md                    # Recommended: Module documentation
```

**Package name:** Can be anything (e.g., `amplifier-module-tool-bash`, `awesome-tools`, `my-package`)

**Module code:** Must be importable Python package

### Entry Point Contract

**Required in pyproject.toml:**

```toml
[project.entry-points."amplifier.modules"]
<module-id> = "<package-code-path>"
```

**Examples:**

```toml
# Microsoft convention
[project]
name = "amplifier-module-tool-bash"

[project.entry-points."amplifier.modules"]
tool-bash = "amplifier_module_tool_bash"

# Community module
[project]
name = "awesome-bash-tools"

[project.entry-points."amplifier.modules"]
awesome-bash = "awesome_bash_tools"
```

**Module ID must match what users specify in profiles.**

### Module Protocol Contract

Modules must implement protocol from amplifier-core:

```python
# Tool protocol
class Tool(Protocol):
    def get_schema(self) -> dict: ...
    async def execute(self, **kwargs) -> dict: ...
```

See [amplifier-core protocols](https://github.com/microsoft/amplifier-core/blob/main/amplifier_core/protocols.py) for full definitions.

---

## Performance Characteristics

### Resolution Speed

| Layer | Typical Time | Notes |
|-------|--------------|-------|
| Env var | < 1ms | Immediate |
| Workspace | < 5ms | Directory check + validation |
| Config file | < 10ms | YAML read + parse |
| Profile | < 1ms | In-memory |
| Package | < 50ms | importlib.metadata |

**Total resolution: < 100ms**

### Git Caching

**First download:**
- Time: 5-30 seconds (repo size, network)
- Disk: Repo size

**Cached usage:**
- Time: < 5ms (directory check)
- Disk: 0 additional

**Cache growth:** Unbounded (manual cleanup via `amplifier module refresh`)

---

## Security

### Source Validation

**File paths:**
- No sandboxing (user controls their filesystem)
- Must exist and be readable

**Git URLs:**
- Standard git authentication (HTTPS credentials, SSH keys)
- SSL validation via git
- User responsible for trusting repositories

**Package sources:**
- Standard Python package security
- No additional validation

### Cache Security

**Location:** `~/.amplifier/module-cache/` (user-owned)
**Permissions:** User read/write only
**Isolation:** Each URL+ref+subdirectory combination gets unique cache directory

---

---

## Related Documentation

- [USER_GUIDE.md](./USER_GUIDE.md) - User guide for customizing module sources
- **[Module Source Protocol](https://github.com/microsoft/amplifier-core/blob/main/docs/MODULE_SOURCE_PROTOCOL.md)** - Kernel contracts
