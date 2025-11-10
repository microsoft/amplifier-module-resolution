---
last_updated: 2025-10-16
status: stable
audience: user
---

# Module Sources: User Guide

**For users who want to customize which modules Amplifier loads.**

This guide explains how to override module sources to use local forks, community modules, or specific versions. If you're just using Amplifier normally, you don't need this—profiles handle everything automatically.

---

## Quick Start

### Using a Community Module

Add to your profile:

```yaml
# ~/.amplifier/profiles/my-profile.md
---
profile:
  name: my-profile
  extends: dev

tools:
  - module: awesome-analyzer
    source: git+https://github.com/community/amplifier-tool-awesome@v1.0.0
---
```

### Using a Fork

```bash
# Override globally (all profiles)
amplifier module link --global tool-bash ~/my-fork/amplifier-module-tool-bash

# Or just for this project
amplifier module link tool-bash ~/my-fork/amplifier-module-tool-bash
```

### Check What's Being Used

```bash
amplifier module status
```

---

## How Module Resolution Works

Amplifier checks 5 places in order. First match wins.

See [SPECIFICATION.md](./SPECIFICATION.md#resolution-order-5-layers) for technical details.

**Quick reference:**

1. **Environment variable** - Temporary override
2. **Workspace convention** - `.amplifier/modules/` if present
3. **Settings** - Merges `.amplifier/settings.yaml` (project) + `~/.amplifier/settings.yaml` (user), project wins
4. **Profile source** - Profile's `source:` field
5. **Installed package** - Standard Python package

---

## Override Methods

### Method 1: Profile Source (Sharing)

Define sources directly in profiles:

```yaml
tools:
  - module: tool-bash
    source: git+https://github.com/microsoft/amplifier-module-tool-bash@v1.2.0

  - module: tool-custom
    source: git+https://github.com/you/custom-tool@main
```

**Use when:** Sharing configuration with project or distributing custom profiles.

### Method 2: Config File (Explicit Overrides)

Create `.amplifier/settings.yaml` (project) or `~/.amplifier/settings.yaml` (user):

```yaml
sources:
  # Local development
  tool-bash: file:///home/user/dev/tool-bash

  # Specific version
  tool-web: git+https://github.com/microsoft/amplifier-module-tool-web@v1.0.0

  # Community module
  tool-jupyter: git+https://github.com/jupyter-amplifier/tool-jupyter@main
```

**Use when:** Developing modules locally, testing forks, project consistency.

**Project vs User:**
- Project (`.amplifier/`) - Commit to git, shared across project
- User (`~/.amplifier/`) - Personal, not committed

### Method 3: CLI Link Command (Quick Override)

```bash
# Link for current project
amplifier module link tool-bash /path/to/local/tool-bash

# Link globally (all projects)
amplifier module link --global tool-bash /path/to/tool-bash

# Remove override
amplifier module unlink tool-bash
amplifier module unlink --global tool-bash
```

**Use when:** Quick local development, testing changes, switching between forks.

### Method 4: Environment Variable (Temporary)

```bash
# Override for this terminal session only
export AMPLIFIER_MODULE_TOOL_BASH=/home/user/dev/tool-bash
amplifier run "test"
```

**Use when:** Debugging specific issue, one-off testing, don't want to modify files.

---

## Source URI Formats

**String format** (simple, recommended):

```yaml
# Git repository
source: git+https://github.com/org/repo@main
source: git+https://github.com/org/repo@v1.0.0
source: git+https://github.com/org/repo@abc123
source: git+https://github.com/org/repo@main#subdirectory=packages/tool

# Local path
source: file:///absolute/path/to/module
source: /absolute/path/to/module
source: ./relative/path

# Package name
source: my-package-name
```

**Object format** (advanced, MCP-aligned):

```yaml
# Git source
source:
  type: git
  url: https://github.com/org/repo
  ref: v1.0.0
  subdirectory: packages/tool  # Optional

# File source
source:
  type: file
  path: /absolute/path/to/module

# Package source
source:
  type: package
  name: package-name
```

See [SPECIFICATION.md](./SPECIFICATION.md#source-field-schema) for complete format specification.

---

## CLI Commands

### User Commands

```bash
# Show module sources
amplifier module status [<module-id>]

# Override module source
amplifier module link <module-id> <source-path>
amplifier module link --global <module-id> <source-path>

# Remove override
amplifier module unlink <module-id>
amplifier module unlink --global <module-id>

# Clear git cache (force re-download)
amplifier module refresh [<module-id>]
amplifier module refresh --all
```

**Example output:**

```bash
$ amplifier module status

Currently Loaded Modules:
┌─────────────────┬────────────────────────────────┬───────────┬────────┐
│ Module          │ Source                         │ Origin    │ Status │
├─────────────────┼────────────────────────────────┼───────────┼────────┤
│ tool-bash       │ file (/home/user/dev/...)      │ user cfg  │ loaded │
│ tool-filesystem │ file (.amplifier/modules/...)  │ workspace │ loaded │
│ tool-web        │ git (microsoft/.../web@main)   │ profile   │ cached │
└─────────────────┴────────────────────────────────┴───────────┴────────┘
```

---

## Common Workflows

### Testing a Fork

```bash
# Clone fork
git clone https://github.com/you/amplifier-module-tool-bash fork-bash
cd fork-bash

# Make changes
# ... edit ...

# Test
export AMPLIFIER_MODULE_TOOL_BASH=$(pwd)
cd ~/project
amplifier run "test bash"
```

### Pinning Versions for Project

```yaml
# .amplifier/settings.yaml (commit to git)
sources:
  tool-bash: git+https://github.com/microsoft/amplifier-module-tool-bash@v1.2.0
  tool-web: git+https://github.com/microsoft/amplifier-module-tool-web@v2.0.1
```

Project collaborators get consistent versions.

### Using Community Modules

```yaml
# ~/.amplifier/profiles/data-science.md
---
profile:
  name: data-science
  extends: dev

tools:
  - module: tool-jupyter
    source: git+https://github.com/jupyter-amplifier/tool-jupyter@v1.0.0

  - module: tool-pandas
    source: git+https://github.com/data-tools/amplifier-pandas@main
---
```

---

## Git Module Caching

### How Caching Works

**First load:** Downloads from git (may be slow)
**Subsequent loads:** Uses cached version (fast)
**Updates:** Manual refresh required

**Cache location:** `~/.amplifier/module-cache/<hash>/<ref>/`

### Refresh Cached Modules

```bash
# Clear all cache
amplifier module refresh --all

# Refresh specific module
amplifier module refresh tool-web
```

---

## Troubleshooting

### Module Not Loading

```bash
# Check resolution
amplifier module status tool-bash --verbose
```

Shows all 6 layers checked and which succeeded/failed.

### Git Clone Failures

Network issues or invalid URLs cause fallback to installed packages:

```
Warn: Failed to download tool-web@main (network error)
Info: Using installed package amplifier-module-tool-web v1.0.0
```

**Solutions:**
- Check network connection
- Verify git URL in profile/config
- For private repos, configure SSH keys or git credentials
- Install package as fallback: `uv pip install <package-name>`

### Conflicting Overrides

```
Warning: Multiple overrides for tool-bash:
  - Project: file:///workspace/tool-bash
  - User: file:///home/user/my-bash
Using: Project (higher priority)
```

See [Resolution Order](./SPECIFICATION.md#resolution-order-5-layers) for priority details.

---

## Best Practices

### For Users

1. **Start with profiles** - Most flexible, shareable
2. **Use project config** - Commit `.amplifier/settings.yaml` for consistency
3. **Use user config for personal forks** - Keep in `~/.amplifier/`
4. **Use env vars for debugging** - Temporary, no files

### For Projects

1. **Pin versions in project config** - Reproducible builds
2. **Document custom modules** - Add to README
3. **Test before committing** - Verify overrides work
4. **Consider profiles** - Better than config for distribution

---

## Related Documentation

- [SPECIFICATION.md](./SPECIFICATION.md) - Technical specification
- **[Profile Authoring](https://github.com/microsoft/amplifier-profiles/blob/main/docs/PROFILE_AUTHORING.md)** - Creating profiles
