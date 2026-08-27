"""Stable Python facade for deterministic Retro Web UI operations."""

from ..scripts.audit_ui import audit
from ..scripts.behavior_guard import SIGNAL_ALGORITHM, compare, snapshot
from ..scripts.bundle_theme import THEMES, build
from ..scripts.inspect_project import detect

__all__ = ["SIGNAL_ALGORITHM", "THEMES", "audit", "build", "compare", "detect", "snapshot"]

