#!/usr/bin/env python3
"""Exercise durable Workspace recovery across a real App Server process loss."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retro_web_ui_gui import __version__
from retro_web_ui_gui.codex_bridge import CodexBridge
from retro_web_ui_gui.controller import AGENT_RESULT_SCHEMA, DesktopController
from retro_web_ui_gui.core_facade import CoreFacade
from retro_web_ui_gui.workflow import ConversionWorkflow
from retro_web_ui_gui.workspace import SessionState, WorkspaceStore


class RecoveryProbeWindow:
    """Minimal presentation port that records recovery safety state."""

    def __init__(self) -> None:
        self.codex_state = "unknown"
        self.busy = False
        self.events: list[Mapping[str, Any]] = []
        self.projects: list[Mapping[str, Any]] = []
        self.sessions: list[Mapping[str, Any]] = []

    def set_codex_state(self, state: str, _message: str) -> None: self.codex_state = state
    def set_project(self, _root: str, _applications=None) -> None: pass
    def set_analysis(self, _result: str) -> None: pass
    def add_agent_event(self, event: Mapping[str, Any]) -> None: self.events.append(dict(event))
    def request_approval(self, _request: Mapping[str, str]) -> bool: return False
    def request_user_input(self, _request: Mapping[str, Any]) -> Mapping[str, list[str]]: return {}
    def set_verification(self, _text: str, *, result: str = "Review required") -> None: pass
    def set_diff(self, _text: str) -> None: pass
    def set_models(self, _models, *, account_text: str = "Signed in with ChatGPT") -> None: pass
    def open_external_url(self, _url: str) -> bool: return False
    def set_busy(self, busy: bool, _message: str | None = None) -> None: self.busy = busy
    def set_workspace_projects(self, projects) -> None: self.projects = list(projects)
    def set_workspace_sessions(self, sessions) -> None: self.sessions = list(sessions)
    def set_session_detail(self, _text: str) -> None: pass
    def set_before_after(self, _before, _after) -> None: pass
    def set_conversion_controls(self, **_values) -> None: pass
    def set_recovery_enabled(self, _enabled: bool) -> None: pass


def git_candidate() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return commit, not status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument("--effort", default="medium")
    args = parser.parse_args(argv)
    candidate_commit, candidate_clean = git_candidate()
    with tempfile.TemporaryDirectory(prefix="retro-web-ui-recovery-smoke-") as temporary:
        root = Path(temporary).resolve()
        project_root = root / "project"
        project_root.mkdir()
        (project_root / "index.html").write_text("<!doctype html><title>Recovery probe</title>\n", encoding="utf-8")
        workspace_root = root / "workspace"
        workspace = WorkspaceStore(workspace_root)
        first_bridge = CodexBridge(
            client_name="retro_web_ui_recovery_smoke",
            client_title="Retro Web UI Recovery Smoke",
            client_version=__version__,
        )
        first_facade = CoreFacade()
        first = DesktopController(
            RecoveryProbeWindow(),
            facade=first_facade,
            workflow=ConversionWorkflow(first_facade),
            bridge=first_bridge,
            workspace=workspace,
        )
        recovered: DesktopController | None = None
        try:
            first.select_project(str(project_root))
            first.select_theme("windows-xp")
            snapshot = first.create_baseline()
            first._begin_workspace_session(snapshot, model=args.model, effort=args.effort)
            availability = first.refresh_codex()
            if not availability.available or not first._codex_ready:
                raise RuntimeError("Live recovery smoke requires Codex with a current ChatGPT sign-in.")
            thread = first_bridge.start_thread(cwd=str(project_root))
            thread_id = first._thread_id(thread)
            first._transition_workspace(SessionState.RUNNING, thread_id=thread_id, model=args.model, reasoning_effort=args.effort)
            turn = first_bridge.start_turn(
                thread_id,
                [{"type": "text", "text": (
                    "Recovery probe only. Do not edit files or run commands. Return classification complete, "
                    "summary RECOVERY_READY, and empty changedFiles, reviewItems, verificationPerformed, "
                    "and verificationUnavailable."
                )}],
                cwd=str(project_root),
                approvalPolicy="on-request",
                sandboxPolicy={"type": "workspaceWrite", "writableRoots": [str(project_root)], "networkAccess": False},
                model=args.model,
                effort=args.effort,
                outputSchema=AGENT_RESULT_SCHEMA,
            )
            turn_id = first._turn_id(turn)
            first._transition_workspace(SessionState.RUNNING, turn_id=turn_id)
            process = first_bridge._process
            if process is None:
                raise RuntimeError("App Server process was not available for the interruption probe.")
            process.kill()
            process.wait(timeout=10)
            first._bridge_started = False
            first._transition_workspace(
                SessionState.TRANSPORT_LOST,
                recovery_reason="Validation intentionally terminated the App Server process after checkpointing IDs.",
            )
            first.close()

            restarted_store = WorkspaceStore(workspace_root)
            window = RecoveryProbeWindow()
            recovered_facade = CoreFacade()
            recovered = DesktopController(
                window,
                facade=recovered_facade,
                workflow=ConversionWorkflow(recovered_facade),
                bridge=CodexBridge(
                    client_name="retro_web_ui_recovery_smoke_restart",
                    client_title="Retro Web UI Recovery Smoke Restart",
                    client_version=__version__,
                ),
                workspace=restarted_store,
            )
            recovered.restore_workspace()
            summary = recovered.recover_session(first.workspace_session_id or "")
            remote_status = str(summary.get("remoteStatus") or "unknown")
            if remote_status not in recovered._active_remote_statuses() | recovered._terminal_remote_statuses():
                raise RuntimeError(f"Durable thread returned an unknown recovery status: {remote_status}")
            session = restarted_store.get_session(first.workspace_project_id or "", first.workspace_session_id or "")
            expected_states = {SessionState.RUNNING, SessionState.INTERRUPTED_RECOVERABLE}
            if session.state not in expected_states:
                raise RuntimeError(f"Recovered session has unsafe state: {session.state.value}")
            persisted = b"\n".join(
                path.read_bytes()
                for path in workspace_root.rglob("*")
                if path.is_file() and path.stat().st_size <= 2_000_000
            )
            if b"RECOVERY_READY" in persisted or b"Recovery probe only" in persisted:
                raise RuntimeError("Raw recovery prompt/output crossed the Workspace persistence boundary.")
            result = {
                "status": "ok",
                "candidateCommit": candidate_commit,
                "candidateClean": candidate_clean,
                "transportInterrupted": True,
                "freshTransport": True,
                "threadIdentity": hashlib.sha256(thread_id.encode("utf-8")).hexdigest()[:16],
                "remoteStatus": remote_status,
                "workspaceState": session.state.value,
                "bindingVerified": bool(summary.get("bindingVerified")),
                "presentationState": window.codex_state,
                "privacyScan": "clean",
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        finally:
            if recovered is not None:
                if recovered.workflow.state.value == "agent_running":
                    recovered.interrupt()
                recovered.close()
            else:
                first.close()


if __name__ == "__main__":
    raise SystemExit(main())
