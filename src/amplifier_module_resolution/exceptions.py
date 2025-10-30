"""Exception types for module resolution.

All exceptions inherit from base exceptions in amplifier-core to maintain
consistent error handling across the system.
"""


class ModuleResolutionError(Exception):
    """Base exception for module resolution failures.

    Attributes:
        message: Error message
        context: Additional context dict for debugging
    """

    def __init__(self, message: str, context: dict | None = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}


class InstallError(ModuleResolutionError):
    """Module installation failed.

    Raised when:
    - Git clone/download fails
    - File copy fails
    - Package not found
    - Subprocess errors during installation
    """

    pass
