"""Module resolver implementations.

Concrete implementation of module resolution with pluggable settings provider.
"""

import logging
import os
from pathlib import Path
from typing import Protocol

from .exceptions import ModuleResolutionError
from .sources import FileSource
from .sources import GitSource
from .sources import PackageSource

logger = logging.getLogger(__name__)


class SettingsProviderProtocol(Protocol):
    """Interface for settings access."""

    def get_module_sources(self) -> dict[str, str]:
        """Get module source overrides from settings."""
        ...


class CollectionModuleProviderProtocol(Protocol):
    """Interface for collection module lookup."""

    def get_collection_modules(self) -> dict[str, str]:
        """Get module_id -> absolute_path mappings from installed collections.

        Returns:
            Dict mapping module IDs to absolute filesystem paths
        """
        ...


class StandardModuleSourceResolver:
    """Standard 6-layer resolution strategy.

    Resolution order (first match wins):
    1. Environment variable (AMPLIFIER_MODULE_<ID>)
    2. Workspace convention (workspace_dirs/<id>/)
    3. Settings provider (merges project + user settings)
    4. Collection modules (registered via installed collections)
    5. Profile hint
    6. Installed package
    """

    def __init__(
        self,
        workspace_dir: Path | list[Path] | None = None,
        settings_provider: SettingsProviderProtocol | None = None,
        collection_provider: CollectionModuleProviderProtocol | None = None,
    ):
        """Initialize resolver with optional configuration.

        Args:
            workspace_dir: Optional workspace directory path(s) (layer 2).
                          Can be a single Path or a list of Paths to search in order.
            settings_provider: Optional settings provider (layer 3)
            collection_provider: Optional collection module provider (layer 4)
        """
        # Normalize workspace_dir to a list for consistent handling
        if workspace_dir is None:
            self.workspace_dirs: list[Path] = []
        elif isinstance(workspace_dir, list):
            self.workspace_dirs = workspace_dir
        else:
            self.workspace_dirs = [workspace_dir]
        # Keep workspace_dir for backwards compatibility (first dir or None)
        self.workspace_dir = self.workspace_dirs[0] if self.workspace_dirs else None
        self.settings_provider = settings_provider
        self.collection_provider = collection_provider

    def resolve(self, module_id: str, profile_hint: str | None = None):
        """Resolve module through 6-layer fallback."""
        source, _layer = self.resolve_with_layer(module_id, profile_hint)
        return source

    def resolve_with_layer(self, module_id: str, profile_hint: str | None = None) -> tuple:
        """Resolve module and return which layer resolved it.

        Returns:
            Tuple of (source, layer_name)
            layer_name is one of: env, workspace, settings, collection, profile, package
        """
        # Layer 1: Environment variable
        env_key = f"AMPLIFIER_MODULE_{module_id.upper().replace('-', '_')}"
        if env_value := os.getenv(env_key):
            logger.debug(f"[module:resolve] {module_id} -> env var ({env_value})")
            return (self._parse_source(env_value, module_id), "env")

        # Layer 2: Workspace convention (search all workspace directories)
        if self.workspace_dirs and (workspace_source := self._check_workspace(module_id)):
            logger.debug(f"[module:resolve] {module_id} -> workspace")
            return (workspace_source, "workspace")

        # Layer 3: Settings provider (collapsed project + user settings)
        if self.settings_provider:
            sources = self.settings_provider.get_module_sources()
            if module_id in sources:
                logger.debug(f"[module:resolve] {module_id} -> settings")
                return (
                    self._parse_source(sources[module_id], module_id),
                    "settings",
                )

        # Layer 4: Collection modules (registered via installed collections)
        if self.collection_provider:
            collection_modules = self.collection_provider.get_collection_modules()
            if module_id in collection_modules:
                module_path = Path(collection_modules[module_id])
                logger.debug(f"[module:resolve] {module_id} -> collection ({module_path})")
                return (FileSource(module_path), "collection")

        # Layer 5: Profile hint
        if profile_hint:
            logger.debug(f"[module:resolve] {module_id} -> profile")
            return (self._parse_source(profile_hint, module_id), "profile")

        # Layer 6: Installed package (fallback)
        logger.debug(f"[module:resolve] {module_id} -> package")
        return (self._resolve_package(module_id), "package")

    def _parse_source(self, source: str | dict, module_id: str):
        """Parse source URI into ModuleSource instance.

        Args:
            source: String URI or dict object
            module_id: Module ID (for error messages)

        Returns:
            ModuleSource instance

        Raises:
            ValueError: Invalid source format
        """
        # Object format (MCP-aligned)
        if isinstance(source, dict):
            source_type = source.get("type")
            if source_type == "git":
                return GitSource(
                    url=source["url"],
                    ref=source.get("ref", "main"),
                    subdirectory=source.get("subdirectory"),
                )
            if source_type == "file":
                return FileSource(source["path"])
            if source_type == "package":
                return PackageSource(source["name"])
            raise ValueError(f"Invalid source type '{source_type}' for module '{module_id}'")

        # String format
        source = str(source)

        if source.startswith("git+"):
            return GitSource.from_uri(source)
        if source.startswith("file://") or source.startswith("/") or source.startswith("."):
            return FileSource(source)
        # Assume package name
        return PackageSource(source)

    def _check_workspace(self, module_id: str) -> FileSource | None:
        """Check workspace convention for module.

        Searches through all workspace directories in order.

        Args:
            module_id: Module identifier (exact name)

        Returns:
            FileSource if found and valid, None otherwise
        """
        if not self.workspace_dirs:
            return None

        # Search through all workspace directories in order
        for workspace_dir in self.workspace_dirs:
            workspace_path = workspace_dir / module_id

            if not workspace_path.exists():
                continue

            # Check for empty submodule (has .git but no code)
            if self._is_empty_submodule(workspace_path):
                logger.debug(f"Module {module_id} workspace dir is empty submodule, skipping")
                continue

            # Check if valid module
            if not any(workspace_path.glob("**/*.py")):
                logger.warning(f"Module {module_id} in workspace but contains no Python files, skipping")
                continue

            return FileSource(workspace_path)

        return None

    def _is_empty_submodule(self, path: Path) -> bool:
        """Check if directory is uninitialized git submodule.

        Args:
            path: Directory to check

        Returns:
            True if empty submodule, False otherwise
        """
        # Has .git file (submodule marker) but no Python files
        git_file = path / ".git"
        return git_file.exists() and git_file.is_file() and not any(path.glob("**/*.py"))

    def _resolve_package(self, module_id: str) -> PackageSource:
        """Resolve to installed package using fallback logic.

        Tries:
        1. Exact module ID as package name
        2. amplifier-module-<id> convention

        Args:
            module_id: Module identifier

        Returns:
            PackageSource

        Raises:
            ModuleResolutionError: Neither package exists
        """
        import importlib.metadata

        # Try exact ID
        try:
            importlib.metadata.distribution(module_id)
            return PackageSource(module_id)
        except importlib.metadata.PackageNotFoundError:
            pass

        # Try convention
        convention_name = f"amplifier-module-{module_id}"
        try:
            importlib.metadata.distribution(convention_name)
            return PackageSource(convention_name)
        except importlib.metadata.PackageNotFoundError:
            pass

        # Both failed - build workspace message
        if self.workspace_dirs:
            workspace_paths = [f"{ws_dir}/{module_id}" for ws_dir in self.workspace_dirs]
            workspace_msg = ", ".join(workspace_paths) + " (none found)"
        else:
            workspace_msg = "N/A"

        raise ModuleResolutionError(
            f"Module '{module_id}' not found\n\n"
            f"Resolution attempted:\n"
            f"  1. Environment: AMPLIFIER_MODULE_{module_id.upper().replace('-', '_')} (not set)\n"
            f"  2. Workspace: {workspace_msg}\n"
            f"  3. Settings: (no entry)\n"
            f"  4. Collections: (no registered module)\n"
            f"  5. Profile: (no source specified)\n"
            f"  6. Package: Tried '{module_id}' and '{convention_name}' (neither installed)\n\n"
            f"Suggestions:\n"
            f"  - Add source to profile: source: git+https://...\n"
            f"  - Add source override to settings\n"
            f"  - Install package: uv pip install <package-name>\n"
            f"  - Install collection with module: amplifier collection add <collection-url>"
        )

    def __repr__(self) -> str:
        return f"StandardModuleSourceResolver(workspaces={self.workspace_dirs}, settings={self.settings_provider is not None})"
