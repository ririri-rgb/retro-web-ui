"""Retro Web UI shared core package."""

from .scripts.contracts import CLI_API_VERSION, TOOL_VERSION

__version__ = TOOL_VERSION

__all__ = ["CLI_API_VERSION", "TOOL_VERSION", "__version__"]

