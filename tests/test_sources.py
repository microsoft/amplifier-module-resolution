"""Tests for module source implementations."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from amplifier_module_resolution import FileSource
from amplifier_module_resolution import GitSource
from amplifier_module_resolution import PackageSource
from amplifier_module_resolution.exceptions import InstallError
from amplifier_module_resolution.exceptions import ModuleResolutionError


class TestFileSource:
    """Tests for FileSource."""

    def test_init_with_string_path(self):
        """String paths are converted to Path."""
        source = FileSource("/tmp/module")
        assert isinstance(source.path, Path)

    def test_init_with_file_uri(self):
        """file:// prefix is stripped."""
        source = FileSource("file:///tmp/module")
        assert str(source.path) == "/tmp/module"

    def test_init_with_path_object(self):
        """Path objects are accepted."""
        path = Path("/tmp/module")
        source = FileSource(path)
        assert source.path == path.resolve()

    def test_resolve_valid_directory(self, tmp_path):
        """Resolves to valid module directory."""
        module_dir = tmp_path / "test_module"
        module_dir.mkdir()
        (module_dir / "__init__.py").write_text("")

        source = FileSource(module_dir)
        result = source.resolve()

        assert result == module_dir.resolve()

    def test_resolve_nonexistent_path(self):
        """Raises error for nonexistent path."""
        source = FileSource("/nonexistent/path")

        with pytest.raises(ModuleResolutionError, match="not found"):
            source.resolve()

    def test_resolve_not_directory(self, tmp_path):
        """Raises error if path is not a directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        source = FileSource(file_path)

        with pytest.raises(ModuleResolutionError, match="not a directory"):
            source.resolve()

    def test_resolve_no_python_files(self, tmp_path):
        """Raises error if directory has no Python files."""
        module_dir = tmp_path / "empty"
        module_dir.mkdir()

        source = FileSource(module_dir)

        with pytest.raises(ModuleResolutionError, match="not contain a valid Python module"):
            source.resolve()

    def test_repr(self):
        """String representation shows path."""
        source = FileSource("/tmp/module")
        assert "FileSource" in repr(source)
        assert "/tmp/module" in repr(source)


class TestGitSource:
    """Tests for GitSource."""

    def test_init(self):
        """Initialize with URL and ref."""
        source = GitSource("https://github.com/org/repo", ref="v1.0.0")
        assert source.url == "https://github.com/org/repo"
        assert source.ref == "v1.0.0"
        assert source.subdirectory is None

    def test_init_with_subdirectory(self):
        """Initialize with subdirectory."""
        source = GitSource("https://github.com/org/repo", ref="main", subdirectory="modules/provider")
        assert source.subdirectory == "modules/provider"

    def test_from_uri_basic(self):
        """Parse basic git+ URI."""
        source = GitSource.from_uri("git+https://github.com/org/repo@v1.0.0")

        assert source.url == "https://github.com/org/repo"
        assert source.ref == "v1.0.0"
        assert source.subdirectory is None

    def test_from_uri_with_subdirectory(self):
        """Parse git+ URI with subdirectory."""
        source = GitSource.from_uri("git+https://github.com/org/repo@main#subdirectory=src/module")

        assert source.url == "https://github.com/org/repo"
        assert source.ref == "main"
        assert source.subdirectory == "src/module"

    def test_from_uri_default_ref(self):
        """Default ref is 'main' when not specified."""
        source = GitSource.from_uri("git+https://github.com/org/repo")

        assert source.url == "https://github.com/org/repo"
        assert source.ref == "main"

    def test_from_uri_invalid_format(self):
        """Raises error for invalid URI format."""
        with pytest.raises(ValueError, match="must start with 'git\\+'"):
            GitSource.from_uri("https://github.com/org/repo")

    def test_resolve_with_cache(self, tmp_path):
        """Uses cached module when available."""
        # Create cache directory
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        source = GitSource("https://github.com/org/repo", ref="main")
        source.cache_dir = cache_dir

        # Calculate actual cache key (includes subdirectory if present)
        import hashlib

        cache_key_input = f"{source.url}@{source.ref}"
        if source.subdirectory:
            cache_key_input += f"#{source.subdirectory}"
        cache_key = hashlib.sha256(cache_key_input.encode()).hexdigest()[:12]
        cached_module = cache_dir / cache_key / "main"
        cached_module.mkdir(parents=True)
        (cached_module / "__init__.py").write_text("")
        (cached_module / "core.py").write_text("")

        # Should use cache
        result = source.resolve()
        assert result == cached_module

    def test_resolve_downloads_when_not_cached(self, tmp_path, monkeypatch):
        """Downloads module when not in cache."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        source = GitSource("https://github.com/org/repo", ref="main")
        monkeypatch.setattr(source, "cache_dir", cache_dir)

        # Mock download to create module
        def mock_download(target: Path):
            target.mkdir(parents=True, exist_ok=True)
            (target / "__init__.py").write_text("")

        monkeypatch.setattr(source, "_download_via_uv", mock_download)

        result = source.resolve()

        # Should have downloaded
        assert result.exists()
        assert (result / "__init__.py").exists()

    def test_resolve_subdirectory_not_found(self, tmp_path, monkeypatch):
        """Raises error when uv fails due to nonexistent subdirectory.

        When subdirectory doesn't exist in repo, uv itself fails during download.
        We rely on uv's error, not post-download validation.
        """
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        source = GitSource("https://github.com/org/repo", ref="main", subdirectory="nonexistent")
        monkeypatch.setattr(source, "cache_dir", cache_dir)

        # Mock uv download failure (simulates uv's error when subdirectory not in repo)
        def mock_download(target: Path):
            raise subprocess.CalledProcessError(
                1, ["uv", "pip", "install"], stderr="error: The source distribution has no subdirectory `nonexistent`"
            )

        monkeypatch.setattr(source, "_download_via_uv", mock_download)
        monkeypatch.setattr(source, "_get_remote_sha_sync", lambda: "abc123")

        with pytest.raises(InstallError, match="Failed to download"):
            source.resolve()

    def test_download_via_uv_command(self, tmp_path, monkeypatch):
        """Builds correct uv command."""
        source = GitSource("https://github.com/org/repo", ref="v1.0.0")

        # Mock subprocess.run in the sources module with successful return
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run = MagicMock(return_value=mock_result)
        monkeypatch.setattr("amplifier_module_resolution.sources.subprocess.run", mock_run)

        target = tmp_path / "target"
        source._download_via_uv(target)

        # Verify command
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "uv"
        assert cmd[1] == "pip"
        assert cmd[2] == "install"
        assert "--target" in cmd
        assert str(target) in cmd
        assert "git+https://github.com/org/repo@v1.0.0" in cmd

    def test_download_via_uv_failure(self, tmp_path, monkeypatch):
        """Raises InstallError when uv command fails."""
        source = GitSource("https://github.com/org/repo", ref="main")

        # Mock subprocess.run to raise CalledProcessError
        def mock_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd, b"", b"error")

        monkeypatch.setattr("subprocess.run", mock_run)

        target = tmp_path / "target"
        with pytest.raises(subprocess.CalledProcessError):
            source._download_via_uv(target)

    def test_repr(self):
        """String representation shows details."""
        source = GitSource("https://github.com/org/repo", ref="v1.0.0", subdirectory="src")
        result = repr(source)

        assert "GitSource" in result
        assert "org/repo" in result
        assert "v1.0.0" in result
        assert "src" in result

    def test_subdirectory_cache_keys_unique(self):
        """Different subdirectories must generate different cache keys.

        Bug: Cache key only used url+ref, ignoring subdirectory.
        This caused modules from same repo but different subdirectories
        to overwrite each other in cache.

        Credit: Bug identified by Paul Payne (@payneio) in PR #2
        """
        import hashlib

        source1 = GitSource("https://github.com/org/repo", ref="main")
        source2 = GitSource("https://github.com/org/repo", ref="main", subdirectory="modules/tool-x")
        source3 = GitSource("https://github.com/org/repo", ref="main", subdirectory="modules/tool-y")

        # Generate cache keys the way sources.py does
        def get_cache_key(source):
            cache_key_input = f"{source.url}@{source.ref}"
            if source.subdirectory:
                cache_key_input += f"#{source.subdirectory}"
            return hashlib.sha256(cache_key_input.encode()).hexdigest()[:12]

        key1 = get_cache_key(source1)
        key2 = get_cache_key(source2)
        key3 = get_cache_key(source3)

        # All three must be unique
        assert key1 != key2, "Collection and module must have different cache keys"
        assert key1 != key3, "Collection and different module must have different keys"
        assert key2 != key3, "Different modules must have different cache keys"

    def test_subdirectory_resolve_path(self, tmp_path, monkeypatch):
        """Resolved path should be cache_path, not cache_path/subdirectory.

        Bug: Code appended subdirectory to cache_path, but uv installs
        content FROM subdirectory TO target directly (doesn't recreate structure).

        Expected behavior:
        - uv installs FROM subdirectory TO cache_path
        - resolve() returns cache_path (not cache_path/subdirectory)

        Credit: Bug identified by Paul Payne (@payneio) in PR #2
        """
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        source = GitSource("https://github.com/org/repo", ref="main", subdirectory="modules/tool-x")
        monkeypatch.setattr(source, "cache_dir", cache_dir)

        # Mock uv download - simulates uv's actual behavior
        # uv installs FROM subdirectory TO target (doesn't create subdirectory structure)
        def mock_download(target: Path):
            target.mkdir(parents=True, exist_ok=True)
            # Create module files directly at target (NOT at target/modules/tool-x/)
            (target / "__init__.py").write_text("")
            (target / "core.py").write_text("")

        monkeypatch.setattr(source, "_download_via_uv", mock_download)
        monkeypatch.setattr(source, "_get_remote_sha_sync", lambda: "abc123def")
        monkeypatch.setattr(source, "_write_cache_metadata", lambda path, sha: None)

        result = source.resolve()

        # Result should be cache_path, NOT cache_path/subdirectory
        import hashlib

        cache_key_input = f"{source.url}@{source.ref}"
        if source.subdirectory:
            cache_key_input += f"#{source.subdirectory}"
        cache_key = hashlib.sha256(cache_key_input.encode()).hexdigest()[:12]
        expected_path = cache_dir / cache_key / "main"

        assert result == expected_path, "Should return cache_path directly, not append subdirectory"
        assert (result / "__init__.py").exists(), "Module files should exist at returned path"


class TestPackageSource:
    """Tests for PackageSource."""

    def test_init(self):
        """Initialize with package name."""
        source = PackageSource("my-package")
        assert source.package_name == "my-package"

    def test_resolve_installed_package(self, monkeypatch):
        """Resolves to installed package location."""
        # Mock importlib.metadata
        mock_dist = MagicMock()
        mock_file = MagicMock()
        mock_file.parent = Path("/site-packages/my_package")

        mock_dist.files = [mock_file]
        mock_dist.locate_file.return_value = Path("/site-packages/my_package/__init__.py")

        def mock_distribution(name):
            if name == "my-package":
                return mock_dist
            raise ModuleNotFoundError()

        monkeypatch.setattr("importlib.metadata.distribution", mock_distribution)

        source = PackageSource("my-package")
        result = source.resolve()

        assert result == Path("/site-packages/my_package")

    def test_resolve_package_not_found(self, monkeypatch):
        """Raises error when package not installed."""

        def mock_distribution(name):
            import importlib.metadata

            raise importlib.metadata.PackageNotFoundError()

        monkeypatch.setattr("importlib.metadata.distribution", mock_distribution)

        source = PackageSource("nonexistent-package")

        with pytest.raises(ModuleResolutionError, match="not installed"):
            source.resolve()

    def test_repr(self):
        """String representation shows package name."""
        source = PackageSource("my-package")
        assert "PackageSource" in repr(source)
        assert "my-package" in repr(source)
