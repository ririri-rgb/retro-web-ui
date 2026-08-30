"""Durable, local workspace records for the desktop application.

This module deliberately knows nothing about Qt, the CLI, or the Codex App
Server.  It persists only redacted, application-owned conversion metadata and
copied evidence.  Remote thread recovery remains the bridge's responsibility.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid
from typing import Any, Mapping, Optional


SCHEMA_VERSION = 1
MAX_ARTIFACT_BYTES = 2_000_000
MAX_ARTIFACTS_PER_SESSION = 64
MAX_SESSIONS_PER_PROJECT = 256
MAX_TEXT_FIELD_BYTES = 16_000
MAX_RECORD_BYTES = 2_000_000
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DURABLE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SENSITIVE = re.compile(r"(?:token|secret|password|authorization|auth[_-]?url|device[_-]?code|email)", re.I)
_TOKEN_VALUE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+[^\s]+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b", re.I)
_QUERY_SECRET = re.compile(r"([?&](?:access_token|refresh_token|token|code|key|secret)=)[^&\s]+", re.I)
_COOKIE_VALUE = re.compile(r"\b(?:Cookie|Set-Cookie):\s*[^\r\n]+", re.I)
_AUTHORIZATION_VALUE = re.compile(r"(?im)\b((?:proxy-)?authorization\s*:\s*)[^\r\n]+")
_LABELED_SECRET = re.compile(r"(?i)\b((?:api[ _-]?key|password|secret)\s*[:=]\s*)[^\s,;]+")
_DEVICE_CODE_VALUE = re.compile(r"(?i)\b((?:device|user)[ _-]?code\s*(?::|=|\bis\b)\s*)[A-Z0-9][A-Z0-9-]{3,}")
_URL_VALUE = re.compile(r"https?://[^\s<>\"']+", re.I)
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S)
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class WorkspaceError(RuntimeError):
    pass


class CorruptRecordError(WorkspaceError):
    pass


class UnsupportedSchemaError(WorkspaceError):
    pass


class SessionState(str, Enum):
    DRAFT = "draft"
    PREPARED = "prepared"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    VERIFYING = "verifying"
    VERIFICATION_PENDING = "verification_pending"
    TRANSPORT_LOST = "transport_lost"
    INTERRUPTED_RECOVERABLE = "interrupted_recoverable"
    COMPLETE = "complete"
    COMPLETE_WITH_REVIEW_ITEMS = "complete_with_review_items"
    REVIEW_REQUIRED = "review_required"
    BEHAVIOR_INCOMPATIBILITY = "behavior_incompatibility"
    FAILED = "failed"
    TERMINAL = "terminal"
    ARCHIVED = "archived"


class IntegrityState(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    CHANGED = "changed"
    NOT_CAPTURED = "not_captured"
    NOT_APPLICABLE = "not_applicable"


_OUTCOME_STATES = {SessionState.TERMINAL, SessionState.COMPLETE, SessionState.COMPLETE_WITH_REVIEW_ITEMS, SessionState.REVIEW_REQUIRED, SessionState.BEHAVIOR_INCOMPATIBILITY, SessionState.FAILED}

_TRANSITIONS = {
    SessionState.DRAFT: {SessionState.PREPARED, SessionState.ARCHIVED, SessionState.FAILED},
    SessionState.PREPARED: {SessionState.AWAITING_APPROVAL, SessionState.RUNNING, SessionState.ARCHIVED, *_OUTCOME_STATES},
    SessionState.AWAITING_APPROVAL: {SessionState.RUNNING, SessionState.TRANSPORT_LOST, SessionState.INTERRUPTED_RECOVERABLE, SessionState.ARCHIVED, *_OUTCOME_STATES},
    SessionState.RUNNING: {SessionState.AWAITING_APPROVAL, SessionState.VERIFYING, SessionState.VERIFICATION_PENDING, SessionState.TRANSPORT_LOST, SessionState.INTERRUPTED_RECOVERABLE, *_OUTCOME_STATES},
    SessionState.VERIFYING: {SessionState.VERIFICATION_PENDING, SessionState.TRANSPORT_LOST, SessionState.INTERRUPTED_RECOVERABLE, *_OUTCOME_STATES},
    SessionState.VERIFICATION_PENDING: {SessionState.VERIFYING, SessionState.TRANSPORT_LOST, SessionState.INTERRUPTED_RECOVERABLE, *_OUTCOME_STATES},
    SessionState.TRANSPORT_LOST: {SessionState.RUNNING, SessionState.INTERRUPTED_RECOVERABLE, SessionState.ARCHIVED, *_OUTCOME_STATES},
    SessionState.INTERRUPTED_RECOVERABLE: {SessionState.RUNNING, SessionState.AWAITING_APPROVAL, SessionState.ARCHIVED, *_OUTCOME_STATES},
    SessionState.TERMINAL: {SessionState.ARCHIVED},
    SessionState.COMPLETE: {SessionState.ARCHIVED},
    SessionState.COMPLETE_WITH_REVIEW_ITEMS: {SessionState.ARCHIVED},
    SessionState.REVIEW_REQUIRED: {SessionState.ARCHIVED},
    SessionState.BEHAVIOR_INCOMPATIBILITY: {SessionState.ARCHIVED},
    SessionState.FAILED: {SessionState.ARCHIVED},
    SessionState.ARCHIVED: set(),
}


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    canonical_root: str
    display_name: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ArtifactStatus:
    name: str
    integrity: IntegrityState
    path: Optional[str] = None
    sha256: Optional[str] = None
    bytes: Optional[int] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    project_id: str
    selected_app: str
    theme: Optional[str]
    state: SessionState
    created_at: str
    updated_at: str
    thread_id: Optional[str] = None
    turn_id: Optional[str] = None
    classification: Optional[str] = None
    artifacts: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    failure_reason: Optional[str] = None
    recovery_reason: Optional[str] = None


def default_workspace_root() -> Path:
    """Return an application-private, platform-appropriate data location."""
    return _workspace_root_for(os.name, sys.platform, os.environ, Path.home())


def _workspace_root_for(os_name: str, platform: str, environment: Mapping[str, str], home: Path) -> Path:
    """Pure platform decision helper used by cross-platform regression tests."""
    if os_name == "nt":
        base = environment.get("LOCALAPPDATA") or environment.get("APPDATA") or str(home / "AppData" / "Local")
        return Path(base) / "Retro Web UI"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Retro Web UI"
    base = environment.get("XDG_STATE_HOME") or environment.get("XDG_DATA_HOME") or str(home / ".local" / "state")
    return Path(base) / "retro-web-ui"


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_name(name: str) -> str:
    stem = name.split(".", 1)[0].upper() if isinstance(name, str) else ""
    if (
        not isinstance(name, str)
        or not _SAFE_NAME.fullmatch(name)
        or name in {".", ".."}
        or name.endswith((".", " "))
        or stem in _WINDOWS_RESERVED_NAMES
    ):
        raise WorkspaceError("Artifact names must be simple file names.")
    return name


def _is_link_like(path: Path) -> bool:
    """Reject POSIX links and Windows reparse points such as junctions."""
    try:
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0) or 0)
    return bool(reparse and attributes & reparse)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _redact_text(value: str) -> str:
    """Remove credential-bearing free text before it crosses persistence."""
    redacted = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)
    redacted = _COOKIE_VALUE.sub("Cookie: [REDACTED]", redacted)
    redacted = _AUTHORIZATION_VALUE.sub(r"\1[REDACTED]", redacted)
    redacted = _LABELED_SECRET.sub(r"\1[REDACTED]", redacted)
    redacted = _DEVICE_CODE_VALUE.sub(r"\1[REDACTED]", redacted)
    redacted = _QUERY_SECRET.sub(r"\1[REDACTED]", redacted)
    redacted = _TOKEN_VALUE.sub("[REDACTED]", redacted)

    def redact_auth_url(match: re.Match[str]) -> str:
        url = match.group(0)
        lowered = url.lower()
        if re.search(r"https?://[^/@\s]+:[^/@\s]+@", url, re.I) or any(
            marker in lowered for marker in ("/login", "/oauth", "/authorize", "/device")
        ):
            return "[REDACTED LOGIN URL]"
        return url

    return _URL_VALUE.sub(redact_auth_url, redacted)


class WorkspaceStore:
    """File-backed records with per-record isolation and atomic replacement."""

    def __init__(self, root: Path | str, *, max_artifact_bytes: int = MAX_ARTIFACT_BYTES) -> None:
        unresolved_root = Path(root).expanduser()
        if _is_link_like(unresolved_root):
            raise WorkspaceError(f"Workspace root may not be a symlink: {unresolved_root}")
        self.root = unresolved_root.resolve()
        self.max_artifact_bytes = max_artifact_bytes
        if self.max_artifact_bytes <= 0:
            raise ValueError("max_artifact_bytes must be positive")
        self.projects_root = self.root / "projects"
        self.root.mkdir(parents=True, exist_ok=True)
        if _is_link_like(self.projects_root):
            raise WorkspaceError(f"Workspace projects directory may not be a symlink: {self.projects_root}")
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self._private_dir(self.root)
        self._private_dir(self.projects_root)
        self._root_identity = self._directory_identity(self.root)
        self._projects_identity = self._directory_identity(self.projects_root)

    @staticmethod
    def canonical_project_root(value: Path | str) -> Path:
        raw = Path(value).expanduser()
        if _is_link_like(raw):
            raise WorkspaceError(f"Project root may not be a symlink: {raw}")
        resolved = raw.resolve()
        if not resolved.is_dir():
            raise WorkspaceError(f"Project root is not a directory: {resolved}")
        return resolved

    def open_project(self, root: Path | str) -> ProjectRecord:
        self._assert_storage_anchors()
        canonical = self.canonical_project_root(root)
        for directory in self.projects_root.iterdir():
            if _is_link_like(directory) or not directory.is_dir():
                continue
            try:
                record = self._read_project(directory / "project.json")
            except (CorruptRecordError, UnsupportedSchemaError):
                continue
            if record.canonical_root == str(canonical):
                return record
        project_id = str(uuid.uuid4())
        now = _now()
        record = ProjectRecord(project_id, str(canonical), canonical.name or str(canonical), now, now)
        directory = self._project_dir(project_id)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "sessions").mkdir()
        self._private_dir(directory)
        self._private_dir(directory / "sessions")
        self._atomic_json(directory / "project.json", self._project_document(record))
        return record

    def list_projects(self) -> list[ProjectRecord]:
        self._assert_storage_anchors()
        records: list[ProjectRecord] = []
        for directory in self.projects_root.iterdir():
            if _is_link_like(directory) or not directory.is_dir():
                continue
            try:
                records.append(self._read_project(directory / "project.json"))
            except (CorruptRecordError, UnsupportedSchemaError):
                continue
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def create_session(self, project_id: str, *, selected_app: str = ".", theme: Optional[str] = None, model: Optional[str] = None, reasoning_effort: Optional[str] = None) -> SessionRecord:
        project = self.get_project(project_id)
        selected = self._validate_app(project, selected_app)
        sessions_root = self._project_dir(project_id) / "sessions"
        stored_entries = sum(1 for child in sessions_root.iterdir() if child.is_dir() or child.is_symlink())
        if stored_entries >= MAX_SESSIONS_PER_PROJECT:
            raise WorkspaceError("Project session limit reached; archive or export records before creating another.")
        now = _now()
        record = SessionRecord(str(uuid.uuid4()), project_id, selected, theme, SessionState.DRAFT, now, now, model=self._safe_optional_text(model), reasoning_effort=self._safe_optional_text(reasoning_effort))
        directory = self._session_dir(project_id, record.session_id)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "artifacts").mkdir()
        self._private_dir(directory)
        self._private_dir(directory / "artifacts")
        self._write_session(record)
        return record

    def get_project(self, project_id: str) -> ProjectRecord:
        return self._read_project(self._project_dir(project_id) / "project.json")

    def get_session(self, project_id: str, session_id: str) -> SessionRecord:
        return self._read_session(self._session_dir(project_id, session_id) / "session.json")

    def list_sessions(self, project_id: str) -> list[SessionRecord]:
        directory = self._project_dir(project_id) / "sessions"
        if not directory.is_dir():
            return []
        result: list[SessionRecord] = []
        for child in directory.iterdir():
            if _is_link_like(child) or not child.is_dir():
                continue
            try:
                result.append(self._read_session(child / "session.json"))
            except (CorruptRecordError, UnsupportedSchemaError):
                continue
        return sorted(result, key=lambda item: item.updated_at, reverse=True)

    def list_issues(self) -> list[Mapping[str, str]]:
        """Surface unusable records instead of silently treating them as absent."""
        self._assert_storage_anchors()
        issues: list[Mapping[str, str]] = []
        for directory in self.projects_root.iterdir():
            if _is_link_like(directory):
                issues.append({"kind": "project_directory", "path": str(directory), "error": "symlinked project directory rejected"})
                continue
            if not directory.is_dir():
                continue
            project_path = directory / "project.json"
            try:
                project = self._read_project(project_path)
            except (CorruptRecordError, UnsupportedSchemaError) as error:
                issues.append({"kind": "project_record", "path": str(project_path), "error": str(error)})
                continue
            sessions = directory / "sessions"
            if not sessions.is_dir():
                issues.append({"kind": "session_directory", "path": str(sessions), "error": "missing sessions directory"})
                continue
            for child in sessions.iterdir():
                if _is_link_like(child):
                    issues.append({"kind": "session_directory", "path": str(child), "error": "symlinked session directory rejected", "projectId": project.project_id})
                    continue
                if not child.is_dir():
                    continue
                path = child / "session.json"
                try:
                    self._read_session(path)
                except (CorruptRecordError, UnsupportedSchemaError) as error:
                    issues.append({"kind": "session_record", "path": str(path), "error": str(error), "projectId": project.project_id})
        return issues

    def transition(self, project_id: str, session_id: str, state: SessionState, *, classification: Optional[str] = None, thread_id: Optional[str] = None, turn_id: Optional[str] = None, clear_turn_id: bool = False, model: Optional[str] = None, reasoning_effort: Optional[str] = None, failure_reason: Optional[str] = None, recovery_reason: Optional[str] = None) -> SessionRecord:
        current = self.get_session(project_id, session_id)
        if state != current.state and state not in _TRANSITIONS[current.state]:
            raise WorkspaceError(f"Invalid session transition: {current.state.value} -> {state.value}")
        now = _now()
        started_at = current.started_at or (now if state == SessionState.RUNNING else None)
        terminal = {SessionState.TERMINAL, SessionState.COMPLETE, SessionState.COMPLETE_WITH_REVIEW_ITEMS, SessionState.REVIEW_REQUIRED, SessionState.BEHAVIOR_INCOMPATIBILITY, SessionState.FAILED, SessionState.ARCHIVED}
        record = SessionRecord(
            current.session_id, current.project_id, current.selected_app, current.theme, state, current.created_at, _now(),
            current.thread_id if thread_id is None else self._safe_identifier(thread_id),
            None if clear_turn_id else (current.turn_id if turn_id is None else self._safe_identifier(turn_id)),
            current.classification if classification is None else self._safe_text(classification), current.artifacts,
            current.model if model is None else self._safe_text(model),
            current.reasoning_effort if reasoning_effort is None else self._safe_text(reasoning_effort),
            started_at, current.ended_at or (now if state in terminal else None),
            current.failure_reason if failure_reason is None else self._safe_text(failure_reason),
            current.recovery_reason if recovery_reason is None else self._safe_text(recovery_reason),
        )
        self._write_session(record)
        return record

    def reconcile_startup(self) -> list[SessionRecord]:
        """Mark work interrupted by process termination as safely recoverable."""
        recovered: list[SessionRecord] = []
        for project in self.list_projects():
            for session in self.list_sessions(project.project_id):
                if session.state in {SessionState.RUNNING, SessionState.VERIFYING, SessionState.AWAITING_APPROVAL, SessionState.VERIFICATION_PENDING}:
                    recovered.append(self.transition(project.project_id, session.session_id, SessionState.TRANSPORT_LOST, recovery_reason="The desktop application stopped before this nonterminal session completed."))
        return recovered

    def capture_artifact(self, project_id: str, session_id: str, name: str, source: Path | str, *, allowed_root: Path | str | None = None) -> ArtifactStatus:
        name = _safe_name(name)
        session = self.get_session(project_id, session_id)
        source_path = Path(source)
        if _is_link_like(source_path) or not source_path.is_file():
            raise WorkspaceError("Artifact source must be a regular non-symlink file.")
        resolved = source_path.resolve()
        if allowed_root is not None:
            unresolved_root = Path(allowed_root).expanduser()
            if _is_link_like(unresolved_root):
                raise WorkspaceError("Artifact allowed root may not be a symlink or reparse point.")
            root = unresolved_root.resolve()
            absolute_source = source_path.expanduser().absolute()
            self._reject_link_like_traversal(root, absolute_source)
            try:
                resolved.relative_to(root)
            except ValueError as error:
                raise WorkspaceError("Artifact source is outside its allowed root.") from error
        content = self._read_bounded_regular(resolved, self.max_artifact_bytes)
        return self.capture_bytes(project_id, session_id, name, content)

    def capture_bytes(self, project_id: str, session_id: str, name: str, content: bytes) -> ArtifactStatus:
        """Capture already-redacted, bounded evidence without an intermediary file."""
        name = _safe_name(name)
        session = self.get_session(project_id, session_id)
        if not isinstance(content, bytes):
            raise WorkspaceError("Artifact content must be bytes.")
        if len(content) > self.max_artifact_bytes:
            raise WorkspaceError(f"Artifact exceeds {self.max_artifact_bytes} byte limit.")
        if name not in session.artifacts and len(session.artifacts) >= MAX_ARTIFACTS_PER_SESSION:
            raise WorkspaceError("Session artifact limit reached.")
        collision = next((stored for stored in session.artifacts if stored != name and stored.casefold() == name.casefold()), None)
        if collision is not None:
            raise WorkspaceError(f"Artifact name collides under portable case rules: {collision}")
        destination = self._artifact_dir(project_id, session_id) / name
        self._atomic_bytes(destination, content)
        artifacts = dict(session.artifacts)
        artifacts[name] = {"path": f"artifacts/{name}", "sha256": _digest(content), "bytes": len(content)}
        updated = replace(session, updated_at=_now(), artifacts=artifacts)
        self._write_session(updated)
        return self.artifact_status(project_id, session_id, name)

    def capture_json(self, project_id: str, session_id: str, name: str, value: Mapping[str, Any]) -> ArtifactStatus:
        """Capture a JSON artifact after rejecting obvious credential-bearing keys."""
        if not isinstance(value, Mapping):
            raise WorkspaceError("JSON artifact must be an object.")
        self._reject_sensitive_keys(value)
        return self.capture_bytes(project_id, session_id, name, _json_bytes(self._redact_token_values(value)))

    def mark_artifact_not_applicable(self, project_id: str, session_id: str, name: str) -> ArtifactStatus:
        name = _safe_name(name)
        session = self.get_session(project_id, session_id)
        artifacts = dict(session.artifacts)
        artifacts[name] = {"integrity": IntegrityState.NOT_APPLICABLE.value}
        self._write_session(replace(session, updated_at=_now(), artifacts=artifacts))
        return self.artifact_status(project_id, session_id, name)

    def artifact_status(self, project_id: str, session_id: str, name: str) -> ArtifactStatus:
        name = _safe_name(name)
        session = self.get_session(project_id, session_id)
        entry = session.artifacts.get(name)
        if not isinstance(entry, Mapping):
            return ArtifactStatus(name, IntegrityState.NOT_CAPTURED)
        if entry.get("integrity") == IntegrityState.NOT_APPLICABLE.value:
            return ArtifactStatus(name, IntegrityState.NOT_APPLICABLE)
        relative = entry.get("path")
        digest = entry.get("sha256")
        expected_size = entry.get("bytes")
        if not isinstance(relative, str) or not isinstance(digest, str) or not isinstance(expected_size, int):
            return ArtifactStatus(name, IntegrityState.MISSING, reason="invalid manifest entry")
        if relative != f"artifacts/{name}":
            return ArtifactStatus(name, IntegrityState.MISSING, reason="artifact path does not match its manifest name")
        artifact_root = self._artifact_dir(project_id, session_id).resolve()
        unresolved = self._session_dir(project_id, session_id) / relative
        if _is_link_like(unresolved):
            return ArtifactStatus(name, IntegrityState.MISSING, reason="artifact file is a symlink")
        candidate = unresolved.resolve()
        try:
            candidate.relative_to(artifact_root)
        except ValueError:
            return ArtifactStatus(name, IntegrityState.MISSING, reason="artifact path escapes session")
        if not candidate.is_file():
            return ArtifactStatus(name, IntegrityState.MISSING, reason="artifact file missing")
        try:
            observed_size = candidate.stat().st_size
        except OSError:
            return ArtifactStatus(name, IntegrityState.MISSING, reason="artifact file unavailable")
        if observed_size != expected_size or observed_size > self.max_artifact_bytes:
            return ArtifactStatus(name, IntegrityState.CHANGED, str(candidate), digest, expected_size, "size mismatch")
        try:
            content = self._read_bounded_regular(candidate, self.max_artifact_bytes)
        except WorkspaceError as error:
            return ArtifactStatus(name, IntegrityState.CHANGED, str(candidate), digest, expected_size, str(error))
        if len(content) != expected_size or _digest(content) != digest:
            return ArtifactStatus(name, IntegrityState.CHANGED, str(candidate), digest, expected_size, "digest mismatch")
        return ArtifactStatus(name, IntegrityState.AVAILABLE, str(candidate), digest, expected_size)

    def compare_sessions(self, project_id: str, left_session_id: str, right_session_id: str) -> Mapping[str, Any]:
        left = self.get_session(project_id, left_session_id)
        right = self.get_session(project_id, right_session_id)
        names = sorted(set(left.artifacts) | set(right.artifacts))
        artifacts: dict[str, Mapping[str, str]] = {}
        for name in names:
            first, second = self.artifact_status(project_id, left.session_id, name), self.artifact_status(project_id, right.session_id, name)
            if first.integrity != IntegrityState.AVAILABLE or second.integrity != IntegrityState.AVAILABLE:
                outcome = "incomplete"
            elif first.sha256 == second.sha256:
                outcome = "same"
            else:
                outcome = "different"
            artifacts[name] = {"outcome": outcome, "left": first.integrity.value, "right": second.integrity.value}
        return {"leftSessionId": left.session_id, "rightSessionId": right.session_id, "artifacts": artifacts}

    def project_availability(self, project_id: str, session_id: Optional[str] = None) -> str:
        project = self.get_project(project_id)
        root = Path(project.canonical_root)
        if not root.is_dir() or _is_link_like(root):
            return "project_missing"
        if session_id is None:
            return "available"
        session = self.get_session(project_id, session_id)
        try:
            self._validate_app(project, session.selected_app)
        except WorkspaceError:
            return "app_missing"
        return "available"

    def _validate_app(self, project: ProjectRecord, app: str) -> str:
        if not isinstance(app, str) or not app:
            raise WorkspaceError("Selected application must be a relative path.")
        root = self.canonical_project_root(project.canonical_root)
        candidate = root / app
        self._reject_symlink_traversal(root, candidate)
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as error:
            raise WorkspaceError("Selected application is outside the project.") from error
        if not resolved.is_dir():
            raise WorkspaceError("Selected application is not a directory.")
        return relative.as_posix() or "."

    @staticmethod
    def _reject_symlink_traversal(root: Path, candidate: Path) -> None:
        """Reject aliases even when they resolve back inside the project."""
        try:
            parts = candidate.relative_to(root).parts
        except ValueError:
            # The later resolved-relative-to check gives the user-facing error.
            return
        current = root
        for part in parts:
            current = current / part
            if _is_link_like(current):
                raise WorkspaceError(f"Selected application traverses a symlink: {current}")

    @staticmethod
    def _reject_link_like_traversal(root: Path, candidate: Path) -> None:
        try:
            parts = candidate.relative_to(root).parts
        except ValueError:
            return
        current = root
        for part in parts:
            current = current / part
            if _is_link_like(current):
                raise WorkspaceError(f"Artifact source traverses a symlink or reparse point: {current}")

    @staticmethod
    def _safe_identifier(value: str) -> str:
        if not isinstance(value, str) or not _DURABLE_IDENTIFIER.fullmatch(value):
            raise WorkspaceError("Invalid durable identifier.")
        return value

    @staticmethod
    def _safe_record_id(value: str) -> str:
        if not isinstance(value, str):
            raise WorkspaceError("Invalid workspace record identifier.")
        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError) as error:
            raise WorkspaceError("Workspace project/session identifiers must be UUIDs.") from error
        canonical = str(parsed)
        if value != canonical:
            raise WorkspaceError("Workspace project/session identifier is not canonical.")
        return canonical

    @staticmethod
    def _safe_text(value: str) -> str:
        if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_TEXT_FIELD_BYTES:
            raise WorkspaceError("Text field is too large.")
        return _redact_text(value)

    @staticmethod
    def _safe_optional_text(value: Optional[str]) -> Optional[str]:
        return None if value is None else WorkspaceStore._safe_text(value)

    @staticmethod
    def _reject_sensitive_keys(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if _SENSITIVE.search(str(key)):
                    raise WorkspaceError(f"JSON artifact contains sensitive field: {key}")
                WorkspaceStore._reject_sensitive_keys(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                WorkspaceStore._reject_sensitive_keys(item)

    @staticmethod
    def _redact_token_values(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): WorkspaceStore._redact_token_values(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [WorkspaceStore._redact_token_values(item) for item in value]
        if isinstance(value, str):
            return _redact_text(value)
        return value

    @staticmethod
    def _directory_identity(path: Path) -> tuple[int, int]:
        if _is_link_like(path):
            raise WorkspaceError(f"Workspace directory may not be a symlink or reparse point: {path}")
        try:
            info = path.lstat()
        except OSError as error:
            raise WorkspaceError(f"Workspace directory is unavailable: {path}") from error
        if not stat.S_ISDIR(info.st_mode):
            raise WorkspaceError(f"Workspace path is not a directory: {path}")
        return int(info.st_dev), int(info.st_ino)

    def _assert_storage_anchors(self) -> None:
        """Fail closed if an initialized storage root was replaced or linked."""
        if self._directory_identity(self.root) != self._root_identity:
            raise WorkspaceError("Workspace root identity changed after initialization.")
        if self._directory_identity(self.projects_root) != self._projects_identity:
            raise WorkspaceError("Workspace projects directory identity changed after initialization.")

    def _project_dir(self, project_id: str) -> Path:
        self._assert_storage_anchors()
        path = self.projects_root / self._safe_record_id(project_id)
        if _is_link_like(path):
            raise WorkspaceError(f"Workspace project directory may not be a symlink: {path}")
        return path

    def _session_dir(self, project_id: str, session_id: str) -> Path:
        project = self._project_dir(project_id)
        sessions = project / "sessions"
        if _is_link_like(sessions):
            raise WorkspaceError(f"Workspace sessions directory may not be a symlink: {sessions}")
        path = sessions / self._safe_record_id(session_id)
        if _is_link_like(path):
            raise WorkspaceError(f"Workspace session directory may not be a symlink: {path}")
        return path

    def _artifact_dir(self, project_id: str, session_id: str) -> Path:
        path = self._session_dir(project_id, session_id) / "artifacts"
        if _is_link_like(path):
            raise WorkspaceError(f"Workspace artifact directory may not be a symlink: {path}")
        return path

    @staticmethod
    def _read_bounded_regular(path: Path, limit: int) -> bytes:
        """Read a regular file without following its final symlink and with a hard cap."""
        if _is_link_like(path):
            raise WorkspaceError("File link or reparse point could not be opened safely.")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(str(path), flags)
        except OSError as error:
            raise WorkspaceError("Artifact file could not be opened safely.") from error
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise WorkspaceError("Artifact source must be a regular file.")
            if info.st_size > limit:
                raise WorkspaceError(f"Artifact exceeds {limit} byte limit.")
            chunks: list[bytes] = []
            remaining = limit + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            content = b"".join(chunks)
            if len(content) > limit:
                raise WorkspaceError(f"Artifact exceeds {limit} byte limit.")
            if len(content) != info.st_size:
                raise WorkspaceError("Artifact changed while it was being read.")
            return content
        finally:
            os.close(descriptor)

    @staticmethod
    def _project_document(record: ProjectRecord) -> Mapping[str, Any]:
        return {"schemaVersion": SCHEMA_VERSION, "kind": "project", "record": asdict(record)}

    @staticmethod
    def _session_document(record: SessionRecord) -> Mapping[str, Any]:
        data = asdict(record)
        data["state"] = record.state.value
        return {"schemaVersion": SCHEMA_VERSION, "kind": "session", "record": data}

    def _write_session(self, record: SessionRecord) -> None:
        self._atomic_json(self._session_dir(record.project_id, record.session_id) / "session.json", self._session_document(record))

    def _read_project(self, path: Path) -> ProjectRecord:
        if _is_link_like(path.parent):
            raise CorruptRecordError(f"Symlinked project directory rejected: {path.parent}")
        record = self._read_document(path, "project")
        try:
            parsed = ProjectRecord(**record)
            if self._safe_record_id(parsed.project_id) != path.parent.name:
                raise ValueError("project identifier does not match its directory")
            return parsed
        except (TypeError, ValueError, WorkspaceError) as error:
            raise CorruptRecordError(f"Invalid project record: {path}") from error

    def _read_session(self, path: Path) -> SessionRecord:
        if _is_link_like(path.parent) or _is_link_like(path.parents[1]) or _is_link_like(path.parents[2]):
            raise CorruptRecordError(f"Symlinked session path rejected: {path}")
        record = self._read_document(path, "session")
        try:
            record = dict(record)
            record["state"] = SessionState(record["state"])
            artifacts = record.get("artifacts", {})
            if not isinstance(artifacts, dict):
                raise ValueError("artifacts is not an object")
            record["artifacts"] = artifacts
            parsed = SessionRecord(**record)
            if self._safe_record_id(parsed.session_id) != path.parent.name:
                raise ValueError("session identifier does not match its directory")
            if self._safe_record_id(parsed.project_id) != path.parents[2].name:
                raise ValueError("session project identifier does not match its directory")
            return parsed
        except (TypeError, ValueError, KeyError, WorkspaceError) as error:
            raise CorruptRecordError(f"Invalid session record: {path}") from error

    @staticmethod
    def _read_document(path: Path, expected_kind: str) -> Mapping[str, Any]:
        try:
            value = json.loads(WorkspaceStore._read_bounded_regular(path, MAX_RECORD_BYTES).decode("utf-8"))
        except (WorkspaceError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CorruptRecordError(f"Unreadable workspace record: {path}") from error
        if not isinstance(value, Mapping) or value.get("kind") != expected_kind:
            raise CorruptRecordError(f"Wrong workspace record type: {path}")
        version = value.get("schemaVersion")
        if not isinstance(version, int):
            raise CorruptRecordError(f"Missing schema version: {path}")
        if version > SCHEMA_VERSION:
            raise UnsupportedSchemaError(f"Workspace record uses newer schema {version}: {path}")
        if version != SCHEMA_VERSION:
            value = WorkspaceStore._migrate(dict(value), version)
        record = value.get("record")
        if not isinstance(record, Mapping):
            raise CorruptRecordError(f"Missing record object: {path}")
        return record

    @staticmethod
    def _migrate(value: dict[str, Any], version: int) -> dict[str, Any]:
        # v1 is the first released format. Keeping this explicit makes future
        # migrations auditable and ensures old records are never guessed at.
        raise UnsupportedSchemaError(f"No migration available from schema {version}")

    @staticmethod
    def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
        WorkspaceStore._atomic_bytes(path, _json_bytes(value))

    @staticmethod
    def _atomic_bytes(path: Path, content: bytes) -> None:
        if _is_link_like(path.parent):
            raise WorkspaceError(f"Workspace destination directory may not be a symlink or reparse point: {path.parent}")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as stream:
                WorkspaceStore._private_file(Path(temp_name))
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
            WorkspaceStore._private_file(path)
            try:
                directory_fd = os.open(str(path.parent), os.O_RDONLY)
            except OSError:
                return
            try:
                os.fsync(directory_fd)
            except OSError:
                # Directory fsync is not supported by Windows and some mounted
                # filesystems. The file fsync and atomic replace above remain
                # mandatory; directory durability is best effort.
                pass
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _private_dir(path: Path) -> None:
        """Best-effort privacy on POSIX; Windows ACLs remain OS-managed."""
        if os.name != "nt":
            try:
                os.chmod(path, 0o700)
            except OSError:
                pass

    @staticmethod
    def _private_file(path: Path) -> None:
        if os.name != "nt":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
