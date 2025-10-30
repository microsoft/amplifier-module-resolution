"""amplifier-module-resolution - Module source resolution library.

Public API exports for module resolution with pluggable strategies.
"""

from .exceptions import InstallError
from .exceptions import ModuleResolutionError
from .protocols import SettingsProviderProtocol
from .resolvers import StandardModuleSourceResolver
from .sources import FileSource
from .sources import GitSource
from .sources import PackageSource

__all__ = [
    # Exceptions
    "ModuleResolutionError",
    "InstallError",
    # Protocols
    "SettingsProviderProtocol",
    # Sources
    "FileSource",
    "GitSource",
    "PackageSource",
    # Resolvers
    "StandardModuleSourceResolver",
]

__version__ = "0.1.0"
