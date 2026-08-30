"""Executable entry point for the Retro Web UI desktop shell.

The optional ``workflow_factory`` lets the integration package be wired in at
application composition time; importing this module never starts Codex or
creates credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .codex_bridge import redact_secrets


def create_application(workflow_factory: Callable[[], Any] | None = None) -> tuple[Any, Any]:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as error:
        raise RuntimeError(
            "Retro Web UI GUI requires the optional Qt dependency. "
            f"Install it with: pip install 'retro-web-ui-skill[gui]' ({error})"
        ) from error

    from .controller import DesktopController
    from . import __version__
    from .core_facade import CoreFacade
    from .codex_bridge import CodexBridge
    from .widgets import MainWindow
    from .workflow import ConversionWorkflow, WorkflowState
    from .workspace import WorkspaceError, WorkspaceStore, default_workspace_root
    from .xp_style import application_icon, apply_xp_style

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Retro Web UI GUI")
    app.setApplicationDisplayName("Retro Web UI GUI")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Retro Web UI")
    app.setWindowIcon(application_icon())
    apply_xp_style(app)
    window = MainWindow()
    window.setWindowIcon(app.windowIcon())
    if workflow_factory:
        controller = workflow_factory()
    else:
        facade = CoreFacade()
        workflow = ConversionWorkflow(facade)
        workspace_error = None
        try:
            workspace = WorkspaceStore(default_workspace_root())
        except (OSError, WorkspaceError) as error:
            workspace = None
            workspace_error = error
        controller = DesktopController(
            window,
            facade=facade,
            workflow=workflow,
            bridge=CodexBridge(client_version=__version__),
            workspace=workspace,
        )
        if workspace_error is not None:
            window.add_agent_event({
                "kind": "workspace_unavailable",
                "message": "Durable project/session history is unavailable; conversion can continue without persistence.",
                "detail": f"{type(workspace_error).__name__}: {redact_secrets(str(workspace_error))}",
            })

    def report_error(action: str, error: Exception) -> None:
        safe_error = str(redact_secrets(str(error)))
        window.set_busy(False)
        window.set_codex_state("error", f"{action} failed: {type(error).__name__}. Review diagnostics before retrying.")
        window.add_agent_event({"kind": "error", "message": f"{action}: {safe_error}"})

    def prepare_baseline_if_ready() -> None:
        try:
            controller.select_theme(window.theme_combo.currentData()[0])
            if controller.workflow.state == WorkflowState.READY_FOR_BASELINE:
                controller.create_baseline()
            controller.refresh_codex()
        except Exception as error:  # UI boundary: diagnostics remain visible.
            report_error("Preparation", error)

    def select_project(root: str) -> None:
        try:
            controller.select_project(root)
            prepare_baseline_if_ready()
        except Exception as error:
            report_error("Project analysis", error)

    def select_application(app_path: str) -> None:
        try:
            controller.select_application(app_path)
            prepare_baseline_if_ready()
        except Exception as error:
            report_error("Application selection", error)

    def start_conversion() -> None:
        try:
            controller.start_conversion(model=window.selected_model(), effort=window.selected_effort())
        except Exception as error:
            report_error("Conversion start", error)

    def reconnect_codex() -> None:
        try:
            controller.reconnect()
        except Exception as error:
            report_error("Codex reconnect", error)

    def begin_login() -> None:
        try:
            controller.begin_chatgpt_login()
        except Exception as error:
            report_error("ChatGPT sign-in", error)

    def open_registered_project(project_id: str) -> None:
        try:
            controller.open_registered_project(project_id)
            prepare_baseline_if_ready()
        except Exception as error:
            report_error("Registered project", error)

    def inspect_session(session_id: str) -> None:
        try:
            controller.inspect_session(session_id)
        except Exception as error:
            report_error("Session inspection", error)

    def compare_sessions(left: str, right: str) -> None:
        try:
            controller.compare_sessions(left, right)
        except Exception as error:
            report_error("Session comparison", error)

    def recover_session(session_id: str) -> None:
        try:
            controller.recover_session(session_id)
        except Exception as error:
            report_error("Session recovery", error)

    window.project_selected.connect(select_project)
    window.application_selected.connect(select_application)
    window.theme_selected.connect(controller.select_theme)
    window.login_requested.connect(begin_login)
    window.reconnect_requested.connect(reconnect_codex)
    window.conversion_requested.connect(start_conversion)
    window.conversion_cancelled.connect(controller.interrupt)
    window.registered_project_requested.connect(open_registered_project)
    window.session_inspection_requested.connect(inspect_session)
    window.session_comparison_requested.connect(compare_sessions)
    window.session_recovery_requested.connect(recover_session)
    app.aboutToQuit.connect(controller.close)
    # Retain the composition root for the window lifetime and for diagnostics.
    window.controller = controller
    restorer = getattr(controller, "restore_workspace", None)
    if callable(restorer):
        restorer()
    return app, window


def main(argv: list[str] | None = None) -> int:
    from . import __version__

    parser = argparse.ArgumentParser(description="Launch the Retro Web UI desktop GUI.")
    parser.add_argument("--version", action="store_true", help="print the desktop shell version")
    parser.add_argument("--smoke", action="store_true", help="create and exercise the native desktop shell, then exit")
    parser.add_argument("--app-server-smoke", action="store_true", help="during --smoke, initialize the installed Codex App Server")
    parser.add_argument("--workspace-lifecycle-smoke", choices=("create", "restore"), help=argparse.SUPPRESS)
    parser.add_argument("--workspace-smoke-project", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.version:
        print(f"Retro Web UI GUI {__version__}")
        return 0
    if args.workspace_lifecycle_smoke and args.workspace_smoke_project is None:
        parser.error("--workspace-smoke-project is required for the native lifecycle smoke")
    if args.workspace_lifecycle_smoke == "create":
        from .workspace_smoke import create_workspace_lifecycle

        print(json.dumps(create_workspace_lifecycle(args.workspace_smoke_project), ensure_ascii=False, sort_keys=True))
        return 0
    try:
        app, window = create_application()
    except RuntimeError as error:
        parser.error(str(error))
    window.show()
    if args.workspace_lifecycle_smoke == "restore":
        from .workspace_smoke import inspect_workspace_lifecycle

        app.processEvents()
        result = dict(inspect_workspace_lifecycle(window.controller.workspace, args.workspace_smoke_project))
        result.update({
            "windowVisible": window.isVisible(),
            "projectHistoryCount": window.project_history.count(),
            "sessionHistoryCount": window.session_history.count(),
        })
        if result["projectHistoryCount"] != 1 or result["sessionHistoryCount"] != 1:
            raise RuntimeError(f"Native GUI history restoration failed: {result}")
        window.controller.close()
        window.close()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    if args.smoke:
        app.processEvents()
        core = window.controller.facade.info()
        codex = window.controller.availability_detector()
        app_server = "not_requested"
        account_type = None
        app_server_error = None
        if args.app_server_smoke and codex.available:
            try:
                window.controller.bridge.start()
                window.controller._bridge_started = True
                account = window.controller.bridge.account_read()
                account_type = window.controller._account_type(account)
                app_server = "ready"
            except Exception as error:
                app_server = "error"
                app_server_error = type(error).__name__
                print(
                    f"App Server smoke failed: {type(error).__name__}: {redact_secrets(str(error))}",
                    file=sys.stderr,
                )
        result = {
            "status": "ok",
            "version": __version__,
            "windowVisible": window.isVisible(),
            "windowTitle": window.windowTitle(),
            "coreStatus": core.status,
            "manifestCompatible": bool(core.result.get("manifest_compatible")),
            "skillAvailable": window.controller.facade.skill_path.is_file(),
            "codexAvailable": codex.available,
            "codexVersion": codex.version,
            "appServer": app_server,
            "accountState": account_type or "sign_in_required",
            "appServerError": app_server_error,
        }
        window.controller.close()
        window.close()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    from PySide6.QtCore import QTimer

    window.set_codex_state(
        "checking",
        "Checking the installed Codex launcher, App Server, ChatGPT sign-in, and available models…",
    )
    QTimer.singleShot(0, window.controller.refresh_codex)
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
