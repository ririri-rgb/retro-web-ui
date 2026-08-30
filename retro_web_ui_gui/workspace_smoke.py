"""Bounded lifecycle probe used only by native candidate validation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .workspace import IntegrityState, SessionState, WorkspaceError, WorkspaceStore, default_workspace_root


_BASELINE_NAME = "behavior-baseline.json"
_THREAD_ID = "native-workspace-smoke-thread"
_TURN_ID = "native-workspace-smoke-turn"
_PRIVACY_SENTINELS = (
    "NATIVE_BASIC_SECRET",
    "NATIVE-DEVICE-42",
    "NATIVE_QUERY_SECRET",
)


def create_workspace_lifecycle(project_root: Path) -> Mapping[str, Any]:
    """Create one active session so a second process must reconcile it."""
    root = default_workspace_root()
    store = WorkspaceStore(root)
    if store.list_projects():
        raise WorkspaceError("Native workspace smoke requires an empty isolated workspace.")
    project = store.open_project(project_root)
    session = store.create_session(
        project.project_id,
        selected_app="app",
        theme="windows-xp",
        model="native-smoke",
        reasoning_effort="none",
    )
    baseline = store.capture_json(
        project.project_id,
        session.session_id,
        _BASELINE_NAME,
        {
            "summary": (
                "Authorization: Basic NATIVE_BASIC_SECRET\n"
                "device code: NATIVE-DEVICE-42\n"
                "https://example.invalid/login?access_token=NATIVE_QUERY_SECRET"
            ),
            "signals": ["native workspace lifecycle"],
        },
    )
    store.transition(project.project_id, session.session_id, SessionState.PREPARED)
    running = store.transition(
        project.project_id,
        session.session_id,
        SessionState.RUNNING,
        thread_id=_THREAD_ID,
        turn_id=_TURN_ID,
    )
    return {
        "phase": "created",
        "workspaceRoot": str(root.resolve()),
        "projectId": project.project_id,
        "sessionId": running.session_id,
        "state": running.state.value,
        "artifactIntegrity": baseline.integrity.value,
        "artifactSha256": baseline.sha256,
    }


def inspect_workspace_lifecycle(store: WorkspaceStore | None, project_root: Path) -> Mapping[str, Any]:
    """Validate state restored by a fresh native GUI composition root."""
    if store is None:
        raise WorkspaceError("Native GUI did not initialize its workspace.")
    projects = store.list_projects()
    if len(projects) != 1:
        raise WorkspaceError(f"Expected one restored project, found {len(projects)}.")
    project = projects[0]
    if Path(project.canonical_root).resolve() != project_root.resolve():
        raise WorkspaceError("Restored project binding does not match the fixture project.")
    sessions = store.list_sessions(project.project_id)
    if len(sessions) != 1:
        raise WorkspaceError(f"Expected one restored session, found {len(sessions)}.")
    session = sessions[0]
    if session.state != SessionState.TRANSPORT_LOST:
        raise WorkspaceError(f"Restart did not reconcile active work safely: {session.state.value}.")
    artifact = store.artifact_status(project.project_id, session.session_id, _BASELINE_NAME)
    if artifact.integrity != IntegrityState.AVAILABLE or not artifact.path:
        raise WorkspaceError(f"Restored baseline integrity is {artifact.integrity.value}.")
    artifact_bytes = Path(artifact.path).read_bytes()
    if hashlib.sha256(artifact_bytes).hexdigest() != artifact.sha256:
        raise WorkspaceError("Restored baseline digest mismatch.")
    persisted = b"\n".join(
        path.read_bytes()
        for path in store.root.rglob("*")
        if path.is_file() and path.stat().st_size <= 2_000_000
    )
    leaked = [sentinel for sentinel in _PRIVACY_SENTINELS if sentinel.encode("ascii") in persisted]
    if leaked:
        raise WorkspaceError(f"Native workspace privacy scan found prohibited sentinels: {leaked}")
    return {
        "phase": "restored",
        "workspaceRoot": str(store.root),
        "projectId": project.project_id,
        "sessionId": session.session_id,
        "state": session.state.value,
        "projectAvailability": store.project_availability(project.project_id, session.session_id),
        "artifactIntegrity": artifact.integrity.value,
        "artifactSha256": artifact.sha256,
        "privacyScan": "clean",
    }
