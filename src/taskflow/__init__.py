"""taskflow-git — git-native task management."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("taskflow-git")
except PackageNotFoundError:
    # Fallback for local/dev (not installed yet)
    __version__ = "0.0.0"