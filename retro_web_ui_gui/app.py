"""Executable entry point for the Retro Web UI desktop shell.

The optional ``workflow_factory`` lets the integration package be wired in at
application composition time; importing this module never starts Codex or
creates credentials.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any


def create_application(workflow_factory: Callable[[], Any] | None = None) -> tuple[Any, Any]:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as error:
        raise RuntimeError(
            "Retro Web UI GUI requires the optional Qt dependency. "
            "Install it with: pip install 'retro-web-ui-skill[gui]'"
        ) from error

    from .controller import DesktopController
    from .core_facade import CoreFacade
    from .codex_bridge import CodexBridge
    from .widgets import MainWindow
    from .workflow import ConversionWorkflow, WorkflowState
    from .xp_style import apply_xp_style

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Retro Web UI GUI")
    app.setOrganizationName("Retro Web UI")
    apply_xp_style(app)
    window = MainWindow()
    if workflow_factory:
        controller = workflow_factory()
    else:
        facade = CoreFacade()
        workflow = ConversionWorkflow(facade)
        controller = DesktopController(window, facade=facade, workflow=workflow, bridge=CodexBridge(client_version="0.0.0.dev0"))

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
    parser = argparse.ArgumentParser(description="Launch the Retro Web UI desktop GUI.")
    parser.add_argument("--version", action="store_true", help="print the desktop shell version")
    args = parser.parse_args(argv)
    if args.version:
        print("Retro Web UI GUI development shell")
        return 0
    try:
        app, window = create_application()
    except RuntimeError as error:
        parser.error(str(error))
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
