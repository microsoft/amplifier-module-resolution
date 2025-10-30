"""Integration tests for realistic resolution scenarios."""

from unittest.mock import MagicMock

from amplifier_module_resolution import FileSource
from amplifier_module_resolution import GitSource
from amplifier_module_resolution import StandardModuleSourceResolver


class MockSettingsProvider:
    """Mock settings provider for integration tests."""

    def __init__(self, sources: dict[str, str] | None = None):
        self.sources = sources or {}

    def get_module_sources(self) -> dict[str, str]:
        return self.sources


class TestCLIScenario:
    """Test CLI application resolution workflow."""

    def test_complete_cli_workflow(self, tmp_path, monkeypatch):
        """Complete CLI workflow with all layers."""
        # Set up workspace (Layer 2)
        workspace = tmp_path / ".amplifier" / "modules"
        workspace.mkdir(parents=True)
        dev_provider = workspace / "provider-dev"
        dev_provider.mkdir()
        (dev_provider / "__init__.py").write_text("")

        # Set up settings (Layer 3)
        provider = MockSettingsProvider(
            {
                "provider-anthropic": "git+https://github.com/org/custom-anthropic@main",
                "tool-filesystem": "git+https://github.com/org/custom-fs@main",
            }
        )

        # Create resolver
        resolver = StandardModuleSourceResolver(workspace_dir=workspace, settings_provider=provider)

        # Test Layer 1: Environment override
        monkeypatch.setenv(
            "AMPLIFIER_MODULE_PROVIDER_ANTHROPIC",
            "git+https://github.com/team/fork@feature",
        )
        source, layer = resolver.resolve_with_layer("provider-anthropic")
        assert layer == "env"
        assert isinstance(source, GitSource)
        assert "team/fork" in source.url
        monkeypatch.delenv("AMPLIFIER_MODULE_PROVIDER_ANTHROPIC")

        # Test Layer 2: Workspace
        source, layer = resolver.resolve_with_layer("provider-dev")
        assert layer == "workspace"
        assert isinstance(source, FileSource)

        # Test Layer 3: Settings
        source, layer = resolver.resolve_with_layer("tool-filesystem")
        assert layer == "settings"
        assert isinstance(source, GitSource)

        # Test Layer 4: Profile
        source, layer = resolver.resolve_with_layer(
            "tool-bash", profile_hint="git+https://github.com/microsoft/tool-bash@main"
        )
        assert layer == "profile"


class TestWebScenario:
    """Test web application resolution workflow."""

    def test_web_no_workspace(self):
        """Web apps don't use workspace convention."""
        # Only settings provider
        provider = MockSettingsProvider(
            {
                "provider-anthropic": "git+https://github.com/org/provider@main",
                "tool-filesystem": "git+https://github.com/org/tool@main",
            }
        )

        resolver = StandardModuleSourceResolver(settings_provider=provider)

        # All resolve from settings
        source1, layer1 = resolver.resolve_with_layer("provider-anthropic")
        source2, layer2 = resolver.resolve_with_layer("tool-filesystem")

        assert layer1 == "settings"
        assert layer2 == "settings"


class TestAirGappedScenario:
    """Test air-gapped deployment resolution."""

    def test_air_gapped_workspace_only(self, tmp_path):
        """Air-gapped uses only workspace directory."""
        # Create local module cache
        cache = tmp_path / "modules"
        cache.mkdir()

        # Pre-populate with modules
        modules = [
            "provider-anthropic",
            "provider-openai",
            "tool-filesystem",
            "tool-bash",
        ]

        for module_name in modules:
            module_dir = cache / module_name
            module_dir.mkdir()
            (module_dir / "__init__.py").write_text("")
            (module_dir / "core.py").write_text("")

        resolver = StandardModuleSourceResolver(workspace_dir=cache)

        # All resolve from workspace
        for module_name in modules:
            source, layer = resolver.resolve_with_layer(module_name)
            assert layer == "workspace"
            assert isinstance(source, FileSource)


class TestDevelopmentWorkflow:
    """Test local development workflow."""

    def test_local_dev_override(self, tmp_path):
        """Local development overrides production sources."""
        # Create workspace for local development
        workspace = tmp_path / "dev-workspace"
        workspace.mkdir()

        # Local development version
        local_provider = workspace / "provider-anthropic"
        local_provider.mkdir()
        (local_provider / "__init__.py").write_text("# Local dev version")

        # Production settings
        provider = MockSettingsProvider({"provider-anthropic": "git+https://github.com/microsoft/provider@v1.0.0"})

        resolver = StandardModuleSourceResolver(workspace_dir=workspace, settings_provider=provider)

        # Workspace takes precedence
        source, layer = resolver.resolve_with_layer("provider-anthropic")
        assert layer == "workspace"
        assert isinstance(source, FileSource)


class TestEmptySubmoduleHandling:
    """Test handling of uninitialized git submodules."""

    def test_empty_submodule_skipped(self, tmp_path):
        """Empty submodules are skipped in resolution."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create empty submodule (has .git file but no Python files)
        submodule = workspace / "provider-anthropic"
        submodule.mkdir()
        (submodule / ".git").write_text("gitdir: ../../.git/modules/provider-anthropic")

        # Settings fallback
        provider = MockSettingsProvider({"provider-anthropic": "git+https://github.com/org/provider@main"})

        resolver = StandardModuleSourceResolver(workspace_dir=workspace, settings_provider=provider)

        # Should skip workspace and use settings
        source, layer = resolver.resolve_with_layer("provider-anthropic")
        assert layer == "settings"


class TestLayerPrecedence:
    """Test layer precedence behavior."""

    def test_environment_overrides_all(self, tmp_path, monkeypatch):
        """Environment variable overrides all other layers."""
        # Set up all layers
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        module_dir = workspace / "test-module"
        module_dir.mkdir()
        (module_dir / "__init__.py").write_text("")

        provider = MockSettingsProvider({"test-module": "git+https://github.com/settings/source@main"})

        resolver = StandardModuleSourceResolver(workspace_dir=workspace, settings_provider=provider)

        # Set environment variable
        monkeypatch.setenv("AMPLIFIER_MODULE_TEST_MODULE", "git+https://github.com/env/override@main")

        # Environment wins
        source, layer = resolver.resolve_with_layer("test-module")
        assert layer == "env"
        assert "env/override" in source.url

    def test_workspace_overrides_settings(self, tmp_path):
        """Workspace overrides settings."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        module_dir = workspace / "test-module"
        module_dir.mkdir()
        (module_dir / "__init__.py").write_text("")

        provider = MockSettingsProvider({"test-module": "git+https://github.com/settings/source@main"})

        resolver = StandardModuleSourceResolver(workspace_dir=workspace, settings_provider=provider)

        # Workspace wins
        source, layer = resolver.resolve_with_layer("test-module")
        assert layer == "workspace"

    def test_settings_overrides_profile(self):
        """Settings override profile hint."""
        provider = MockSettingsProvider({"test-module": "git+https://github.com/settings/source@main"})

        resolver = StandardModuleSourceResolver(settings_provider=provider)

        # Settings wins
        source, layer = resolver.resolve_with_layer(
            "test-module", profile_hint="git+https://github.com/profile/hint@main"
        )
        assert layer == "settings"


class TestMultipleModuleResolution:
    """Test resolving multiple modules in one session."""

    def test_mixed_resolution_sources(self, tmp_path, monkeypatch):
        """Different modules resolve from different layers."""
        # Set up workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        local_module = workspace / "local-tool"
        local_module.mkdir()
        (local_module / "__init__.py").write_text("")

        # Set up settings
        provider = MockSettingsProvider({"settings-tool": "git+https://github.com/org/settings-tool@main"})

        # Mock package for fallback
        def mock_distribution(name):
            if name == "package-tool":
                return MagicMock()
            raise ModuleNotFoundError()

        monkeypatch.setattr("importlib.metadata.distribution", mock_distribution)

        resolver = StandardModuleSourceResolver(workspace_dir=workspace, settings_provider=provider)

        # Module 1: Workspace
        source1, layer1 = resolver.resolve_with_layer("local-tool")
        assert layer1 == "workspace"

        # Module 2: Settings
        source2, layer2 = resolver.resolve_with_layer("settings-tool")
        assert layer2 == "settings"

        # Module 3: Profile
        source3, layer3 = resolver.resolve_with_layer(
            "profile-tool", profile_hint="git+https://github.com/org/profile-tool@main"
        )
        assert layer3 == "profile"

        # Module 4: Package
        source4, layer4 = resolver.resolve_with_layer("package-tool")
        assert layer4 == "package"
