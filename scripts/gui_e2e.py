#!/usr/bin/env python3
"""Run the desktop orchestration workflow against a disposable target.

This is a manual validation harness, not a hosted conversion service. It uses
the current user's Codex App Server login, prints no account data, and defaults
to denying agent/target command approvals unless explicitly allowed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
from collections import Counter
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retro_web_ui_gui.codex_bridge import CodexBridge
from retro_web_ui_gui.controller import DesktopController
from retro_web_ui_gui.core_facade import CoreFacade
from retro_web_ui_gui.workflow import ConversionWorkflow
from retro_web_ui_gui.workspace import IntegrityState, WorkspaceStore
from retro_web_ui_gui import __version__


class HeadlessWindow:
    def __init__(self, root: Path, *, allow_agent_commands: bool, allow_target_commands: bool) -> None:
        self.root = root.resolve()
        self.allow_agent_commands = allow_agent_commands
        self.allow_target_commands = allow_target_commands
        self.events: list[dict[str, Any]] = []
        self.states: list[str] = []
        self.result: str | None = None
        self.verification = ""
        self.diff = ""
        self.models: list[Mapping[str, Any]] = []
        self.workspace_projects: list[Mapping[str, Any]] = []
        self.workspace_sessions: list[Mapping[str, Any]] = []

    def set_codex_state(self, state: str, message: str) -> None:
        self.states.append(state)
        self.events.append({"kind": "codex_state", "state": state, "message": message})

    def set_project(self, root: str, applications=None) -> None:
        self.events.append({"kind": "project", "root": root, "applications": list(applications or [])})

    def set_analysis(self, result: str) -> None:
        self.analysis = result

    def add_agent_event(self, event: Mapping[str, Any]) -> None:
        safe = dict(event)
        safe.pop("detail", None)
        self.events.append(safe)

    def request_approval(self, request: Mapping[str, str]) -> bool:
        cwd = Path(request.get("cwd") or self.root).expanduser()
        in_scope = False
        try:
            cwd.resolve().relative_to(self.root)
            in_scope = True
        except (OSError, ValueError):
            pass
        reason = request.get("reason", "")
        is_target_plan = "declared" in reason and "verification" in reason
        allowed = in_scope and (self.allow_target_commands if is_target_plan else self.allow_agent_commands)
        self.events.append({
            "kind": "approval",
            "command": request.get("command"),
            "cwd": str(cwd),
            "allowed": allowed,
        })
        return allowed

    def set_verification(self, text: str, *, result: str = "Review required") -> None:
        self.verification = text
        self.result = result

    def set_diff(self, text: str) -> None:
        self.diff = text

    def set_models(self, models: list[Mapping[str, Any]], *, account_text: str = "Signed in with ChatGPT") -> None:
        self.models = list(models)

    def open_external_url(self, url: str) -> bool:
        # Manual E2E never launches authentication UI. It reports auth_required.
        return False

    def set_workspace_projects(self, projects: list[Mapping[str, Any]]) -> None:
        self.workspace_projects = list(projects)

    def set_workspace_sessions(self, sessions: list[Mapping[str, Any]]) -> None:
        self.workspace_sessions = list(sessions)

    def set_session_detail(self, text: str) -> None:
        self.session_detail = text

    def set_conversion_controls(self, **state: Any) -> None:
        self.command_state = dict(state)

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        self.busy = busy

    def request_user_input(self, request: Mapping[str, Any]) -> Mapping[str, list[str]]:
        return {}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("target", type=Path)
    value.add_argument("--app")
    value.add_argument("--theme", default="windows-xp", choices=("windows-98", "windows-xp", "windows-7", "japanese-freeware-2000s"))
    value.add_argument("--model", default="gpt-5.6-terra")
    value.add_argument("--effort", default="medium")
    value.add_argument("--timeout", type=float, default=900)
    value.add_argument("--approve-agent-commands", action="store_true")
    value.add_argument("--approve-target-commands", action="store_true")
    value.add_argument("--workspace", type=Path, help="external directory for durable Project/Session evidence")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    target = CoreFacade.project_root(args.target)
    qt_app = None
    try:
        from PySide6.QtCore import QCoreApplication

        qt_app = QCoreApplication.instance() or QCoreApplication([])
    except ImportError:
        pass
    window = HeadlessWindow(
        target,
        allow_agent_commands=args.approve_agent_commands,
        allow_target_commands=args.approve_target_commands,
    )
    facade = CoreFacade()
    workflow = ConversionWorkflow(facade)
    bridge = CodexBridge(client_name="retro_web_ui_gui_e2e", client_title="Retro Web UI GUI E2E", client_version=__version__)
    workspace_root = (args.workspace or Path(tempfile.mkdtemp(prefix="retro-web-ui-workspace-e2e-"))).resolve()
    workspace = WorkspaceStore(workspace_root)
    controller = DesktopController(window, facade=facade, workflow=workflow, bridge=bridge, workspace=workspace)
    started = time.monotonic()
    exit_code = 1
    closed = False
    try:
        snapshot = controller.select_project(str(target))
        if args.app:
            snapshot = controller.select_application(args.app)
        if snapshot.state.value == "app_selection_required":
            raise RuntimeError("APP_SELECTION_REQUIRED: pass --app with one detected candidate")
        controller.select_theme(args.theme)
        controller.create_baseline()
        availability = controller.refresh_codex()
        if not availability.available or (window.states and window.states[-1] != "ready"):
            raise RuntimeError("Codex is unavailable or authentication is required")
        advertised = {str(item.get("id") or item.get("model")) for item in window.models}
        if args.model not in advertised:
            raise RuntimeError(f"Requested model is not advertised by this Codex installation: {args.model}")
        controller.start_conversion(model=args.model, effort=args.effort)
        while window.result is None and "error" not in window.states[-1:]:
            if qt_app is not None:
                qt_app.processEvents()
            if time.monotonic() - started > args.timeout:
                controller.interrupt()
                raise TimeoutError("Timed out waiting for conversion completion")
            time.sleep(0.02)
        project_id = controller.workspace_project_id
        session_id = controller.workspace_session_id
        controller.close()
        closed = True
        restarted_store = WorkspaceStore(workspace_root)
        restored = restarted_store.get_session(project_id, session_id) if project_id and session_id else None
        baseline = restarted_store.artifact_status(project_id, session_id, "behavior-baseline.json") if project_id and session_id else None
        summary = {
            "target": str(target),
            "theme": args.theme,
            "classification": window.result,
            "workflow_state": workflow.state.value,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "event_counts": dict(Counter(str(event.get("kind")) for event in window.events)),
            "modified_files": list(workflow.diff.files) if workflow.diff else [],
            "verification_excerpt": window.verification[-4000:],
            "workspace": str(workspace_root),
            "session_id": session_id,
            "restored_state": restored.state.value if restored else None,
            "restored_classification": restored.classification if restored else None,
            "baseline_integrity": baseline.integrity.value if baseline else IntegrityState.NOT_CAPTURED.value,
            "restart_reconciled": len(restarted_store.reconcile_startup()),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        exit_code = 0 if window.result in {"complete", "complete_with_review_items", "review_required"} else 1
    finally:
        if not closed:
            controller.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
