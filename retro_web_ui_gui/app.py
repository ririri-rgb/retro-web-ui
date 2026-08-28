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
from typing import Any


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
        controller = DesktopController(window, facade=facade, workflow=workflow, bridge=CodexBridge(client_version=__version__))

    def report_error(action: str, error: Exception) -> None:
        window.set_busy(False)
        window.set_codex_state("error", f"{action} failed: {type(error).__name__}. Review diagnostics before retrying.")
        window.add_agent_event({"kind": "error", "message": f"{action}: {error}"})

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

    window.project_selected.connect(select_project)
    window.application_selected.connect(select_application)
    window.theme_selected.connect(controller.select_theme)
    window.login_requested.connect(controller.begin_chatgpt_login)
    window.reconnect_requested.connect(controller.reconnect)
    window.conversion_requested.connect(start_conversion)
    window.conversion_cancelled.connect(controller.interrupt)
    app.aboutToQuit.connect(controller.close)
    # Retain the composition root for the window lifetime and for diagnostics.
    window.controller = controller
    return app, window


def main(argv: list[str] | None = None) -> int:
    from . import __version__

    parser = argparse.ArgumentParser(description="Launch the Retro Web UI desktop GUI.")
    parser.add_argument("--version", action="store_true", help="print the desktop shell version")
    parser.add_argument("--smoke", action="store_true", help="create and exercise the native desktop shell, then exit")
    parser.add_argument("--app-server-smoke", action="store_true", help="during --smoke, initialize the installed Codex App Server")
    args = parser.parse_args(argv)
    if args.version:
        print(f"Retro Web UI GUI {__version__}")
        return 0
    try:
        app, window = create_application()
    except RuntimeError as error:
        parser.error(str(error))
    window.show()
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
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
