"""Desktop presentation layer for Retro Web UI.

Importing this package is intentionally dependency-free: the existing CLI and
core can continue to import package metadata on systems which have not opted
into the desktop extra.  Qt is loaded only when a GUI symbol is requested.
"""

from __future__ import annotations

from typing import Any

__version__ = "2.1.2"
__all__ = ["MainWindow", "__version__"]


def __getattr__(name: str) -> Any:
    if name == "MainWindow":
        from .widgets import MainWindow

        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
