"""Tests for module resolver implementations."""

from unittest.mock import MagicMock

import pytest
from amplifier_module_resolution import FileSource
from amplifier_module_resolution import GitSource
from amplifier_module_resolution import ModuleResolutionError
from amplifier_module_resolution import PackageSource
from amplifier_module_resolution import StandardModuleSourceResolver


class MockSettingsProvider:
    """Mock settings provider for testing."""

    def __init__(self, sources: dict[str, str] | None = None):
        self.sources = sources or {}

    def get_module_sources(self) -> dict[str, str]:
        return self.sources


class TestStandardModuleSourceResolver:
    """Tests for StandardModuleSourceResolver."""

    def test_init_defaults(self):
        """Initialize with no configuration."""
        resolver = StandardModuleSourceResolver()
        assert resolver.workspace_dir is None
        assert resolver.settings_provider is None

    def test_init_with_workspace(self, tmp_path):
        """Initialize with workspace directory."""
        resolver = StandardModuleSourceResolver(workspace_dir=tmp_path)
        assert resolver.workspace_dir == tmp_path

    def test_init_with_settings_provider(self):
        """Initialize with settings provider."""
        provider = MockSettingsProvider()
        resolver = StandardModuleSourceResolver(settings_provider=provider)
        assert resolver.settings_provider is provider

    def test_layer1_environment_variable(self, monkeypatch):
        """Layer 1: Environment variable takes precedence."""
        monkeypatch.setenv("AMPLIFIER_MODULE_TEST_MODULE", "git+https://github.com/org/repo@main")

        resolver = StandardModuleSourceResolver()
        source, layer = resolver.resolve_with_layer("test-module")

        assert layer == "env"
        assert isinstance(source, GitSource)
        assert source.url == "https://github.com/org/repo"

    def test_layer2_workspace_convention(self, tmp_path):
        """Layer 2: Workspace convention after env."""
        # Create workspace module
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        module_dir = workspace / "test-module"
        module_dir.mkdir()
        (module_dir / "__init__.py").write_text("")

        resolver = StandardModuleSourceResolver(workspace_dir=workspace)
        source, layer = resolver.resolve_with_layer("test-module")

        assert layer == "workspace"
        assert isinstance(source, FileSource)
        assert source.path == module_dir.resolve()

    def test_layer2_workspace_skips_empty_submodule(self, tmp_path):
        """Layer 2: Skips empty git submodules."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        module_dir = workspace / "test-module"
        module_dir.mkdir()
        # Create .git file (submodule marker) but no Python files
        (module_dir / ".git").write_text("gitdir: ../.git/modules/test-module")

        provider = MockSettingsProvider({"test-module": "git+https://github.com/org/repo@main"})
        resolver = StandardModuleSourceResolver(workspace_dir=workspace, settings_provider=provider)
        source, layer = resolver.resolve_with_layer("test-module")

        # Should skip workspace and use settings
        assert layer == "settings"

    def test_layer3_settings_provider(self):
        """Layer 3: Settings provider after workspace."""
        provider = MockSettingsProvider({"test-module": "git+https://github.com/org/repo@main"})
        resolver = StandardModuleSourceResolver(settings_provider=provider)
        source, layer = resolver.resolve_with_layer("test-module")

        assert layer == "settings"
        assert isinstance(source, GitSource)

    def test_layer4_profile_hint(self):
        """Layer 4: Profile hint after settings."""
        resolver = StandardModuleSourceResolver()
        source, layer = resolver.resolve_with_layer("test-module", profile_hint="git+https://github.com/org/repo@main")

        assert layer == "profile"
        assert isinstance(source, GitSource)

    def test_layer5_package_fallback(self, monkeypatch):
        """Layer 5: Package fallback when nothing else found."""

        def mock_distribution(name):
            if name == "test-module":
                return MagicMock()
            raise ModuleNotFoundError()

        monkeypatch.setattr("importlib.metadata.distribution", mock_distribution)

        resolver = StandardModuleSourceResolver()
        source, layer = resolver.resolve_with_layer("test-module")

        assert layer == "package"
        assert isinstance(source, PackageSource)

    def test_layer5_package_convention(self, monkeypatch):
        """Layer 5: Tries amplifier-module-<id> convention."""
        import importlib.metadata

        def mock_distribution(name):
            if name == "amplifier-module-test-module":
                return MagicMock()
            raise importlib.metadata.PackageNotFoundError()

        monkeypatch.setattr("importlib.metadata.distribution", mock_distribution)

        resolver = StandardModuleSourceResolver()
        source, layer = resolver.resolve_with_layer("test-module")

        assert layer == "package"
        assert isinstance(source, PackageSource)
        assert source.package_name == "amplifier-module-test-module"

    def test_resolution_failure(self, monkeypatch):
        """Raises error when all layers fail."""
        import importlib.metadata

        def mock_distribution(name):
            raise importlib.metadata.PackageNotFoundError()

        monkeypatch.setattr("importlib.metadata.distribution", mock_distribution)

        resolver = StandardModuleSourceResolver()

        with pytest.raises(ModuleResolutionError) as exc_info:
            resolver.resolve("nonexistent-module")

        error = str(exc_info.value)
        assert "not found" in error
        assert "Resolution attempted" in error

    def test_parse_source_git_uri(self):
        """Parses git+ URI strings."""
        resolver = StandardModuleSourceResolver()
        source = resolver._parse_source("git+https://github.com/org/repo@main", "test")

        assert isinstance(source, GitSource)
        assert source.url == "https://github.com/org/repo"

    def test_parse_source_file_uri(self):
        """Parses file:// URI strings."""
        resolver = StandardModuleSourceResolver()
        source = resolver._parse_source("file:///tmp/module", "test")

        assert isinstance(source, FileSource)

    def test_parse_source_relative_path(self):
        """Parses relative path strings."""
        resolver = StandardModuleSourceResolver()
        source = resolver._parse_source("./modules/test", "test")

        assert isinstance(source, FileSource)

    def test_parse_source_package_name(self):
        """Parses plain package names."""
        resolver = StandardModuleSourceResolver()
        source = resolver._parse_source("my-package", "test")

        assert isinstance(source, PackageSource)
        assert source.package_name == "my-package"

    def test_parse_source_dict_git(self):
        """Parses dict format for git source."""
        resolver = StandardModuleSourceResolver()
        source = resolver._parse_source(
            {"type": "git", "url": "https://github.com/org/repo", "ref": "v1.0.0"},
            "test",
        )

        assert isinstance(source, GitSource)
        assert source.url == "https://github.com/org/repo"
        assert source.ref == "v1.0.0"

    def test_parse_source_dict_file(self):
        """Parses dict format for file source."""
        resolver = StandardModuleSourceResolver()
        source = resolver._parse_source({"type": "file", "path": "/tmp/module"}, "test")

        assert isinstance(source, FileSource)

    def test_parse_source_dict_package(self):
        """Parses dict format for package source."""
        resolver = StandardModuleSourceResolver()
        source = resolver._parse_source({"type": "package", "name": "my-package"}, "test")

        assert isinstance(source, PackageSource)

    def test_parse_source_invalid_dict_type(self):
        """Raises error for invalid dict source type."""
        resolver = StandardModuleSourceResolver()

        with pytest.raises(ValueError, match="Invalid source type"):
            resolver._parse_source({"type": "invalid"}, "test")

    def test_resolve_uses_resolve_with_layer(self):
        """resolve() delegates to resolve_with_layer()."""
        resolver = StandardModuleSourceResolver()
        resolver.resolve_with_layer = MagicMock(return_value=(MagicMock(), "profile"))

        resolver.resolve("test-module", profile_hint="source")

        resolver.resolve_with_layer.assert_called_once_with("test-module", "source")

    def test_repr(self, tmp_path):
        """String representation shows configuration."""
        provider = MockSettingsProvider()
        resolver = StandardModuleSourceResolver(workspace_dir=tmp_path, settings_provider=provider)

        result = repr(resolver)
        assert "StandardModuleSourceResolver" in result
        assert "workspace=" in result
        assert "settings=True" in result


class TestResolutionScenarios:
    """Integration tests for realistic scenarios."""

    def test_cli_resolution(self, tmp_path, monkeypatch):
        """CLI scenario: workspace + settings + profile."""
        # Set up workspace
        workspace = tmp_path / ".amplifier" / "modules"
        workspace.mkdir(parents=True)
        dev_module = workspace / "dev-module"
        dev_module.mkdir()
        (dev_module / "__init__.py").write_text("")

        # Set up settings
        provider = MockSettingsProvider({"provider-anthropic": "git+https://github.com/org/custom@main"})

        # Create resolver
        resolver = StandardModuleSourceResolver(workspace_dir=workspace, settings_provider=provider)

        # Layer 2: Workspace (dev module)
        source, layer = resolver.resolve_with_layer("dev-module")
        assert layer == "workspace"
        assert isinstance(source, FileSource)

        # Layer 3: Settings (provider)
        source, layer = resolver.resolve_with_layer("provider-anthropic")
        assert layer == "settings"
        assert isinstance(source, GitSource)

        # Layer 4: Profile (tool)
        source, layer = resolver.resolve_with_layer(
            "tool-bash", profile_hint="git+https://github.com/microsoft/tool@main"
        )
        assert layer == "profile"

    def test_web_resolution_no_workspace(self):
        """Web scenario: settings only (no workspace)."""
        provider = MockSettingsProvider({"provider-anthropic": "git+https://github.com/org/custom@main"})

        resolver = StandardModuleSourceResolver(settings_provider=provider)

        source, layer = resolver.resolve_with_layer("provider-anthropic")
        assert layer == "settings"

    def test_air_gapped_resolution(self, tmp_path, monkeypatch):
        """Air-gapped scenario: workspace only."""
        workspace = tmp_path / "modules"
        workspace.mkdir()

        # Create local modules
        for module_name in ["provider-anthropic", "tool-filesystem"]:
            module_dir = workspace / module_name
            module_dir.mkdir()
            (module_dir / "__init__.py").write_text("")

        resolver = StandardModuleSourceResolver(workspace_dir=workspace)

        # Both resolve from workspace
        source1, layer1 = resolver.resolve_with_layer("provider-anthropic")
        source2, layer2 = resolver.resolve_with_layer("tool-filesystem")

        assert layer1 == "workspace"
        assert layer2 == "workspace"
