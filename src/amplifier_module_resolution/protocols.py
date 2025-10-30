"""Protocol definitions for amplifier-module-resolution.

These protocols define interfaces for dependency injection, allowing apps to
provide settings without creating circular dependencies.
"""

from typing import Protocol


class SettingsProviderProtocol(Protocol):
    """Interface for settings access.

    Apps provide implementation matching their settings system.
    This avoids circular dependencies between library and config system.
    """

    def get_module_sources(self) -> dict[str, str]:
        """Get module source overrides from settings.

        Returns both project and user settings merged with project taking precedence.

        Returns:
            Dict mapping module_id -> source_uri

        Example:
            >>> provider.get_module_sources()
            {
                "provider-anthropic": "git+https://github.com/org/custom@main",
                "tool-filesystem": "file:///home/dev/tools/filesystem"
            }
        """
        ...
