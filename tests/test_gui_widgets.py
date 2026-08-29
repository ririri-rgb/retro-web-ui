"""Headless tests for GUI presentation and its dependency-injection boundary."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from retro_web_ui_gui.widgets import AgentEvent, MainWindow
    QT_AVAILABLE = True
except ImportError:  # CLI-only environments intentionally omit the GUI extra.
    QApplication = None  # type: ignore[assignment]
    AgentEvent = MainWindow = None  # type: ignore[assignment]
    QT_AVAILABLE = False


class FakeWorkflow:
    def __init__(self) -> None:
        self.projects: list[str] = []
        self.themes: list[str] = []
        self.started = 0
        self.cancelled = 0

    def select_project(self, root: str) -> None:
        self.projects.append(root)

    def select_theme(self, theme_id: str) -> None:
        self.themes.append(theme_id)

    def start_conversion(self) -> None:
        self.started += 1

    def cancel(self) -> None:
        self.cancelled += 1


def gui_app():
    assert QApplication is not None
    return QApplication.instance() or QApplication([])


class GuiMetadataTests(unittest.TestCase):
    def test_package_metadata_import_does_not_require_qt(self) -> None:
        """Core/CLI tooling can import GUI metadata before Qt is installed."""
        root = Path(__file__).resolve().parents[1]
        code = """import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith('PySide6'):
        raise AssertionError('Qt imported eagerly')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import retro_web_ui_gui
assert retro_web_ui_gui.__version__
"""
        completed = subprocess.run([sys.executable, "-c", code], cwd=root, check=False, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


@unittest.skipUnless(QT_AVAILABLE, "install the optional [gui] extra to run Qt widget tests")
class GuiWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        gui_app()

    def test_project_theme_models_and_workflow_events_are_injected(self) -> None:
        port = FakeWorkflow()
        window = MainWindow(port)
        self.assertEqual(window.theme_combo.currentData()[0], "windows-xp")
        self.assertIn("Luna", window.theme_description.text())
        window.set_models([
            {
                "id": "gpt-5.6-terra",
                "displayName": "GPT-5.6-Terra",
                "isDefault": True,
                "defaultReasoningEffort": "medium",
                "supportedReasoningEfforts": [{"reasoningEffort": "low"}, {"reasoningEffort": "medium"}],
            }
        ])
        self.assertEqual(window.selected_model(), "gpt-5.6-terra")
        self.assertEqual(window.selected_effort(), "medium")
        window.set_project("/tmp/example", [{"path": "apps/web"}, {"path": "apps/admin"}])
        window.project_selected.emit("/tmp/example")
        window.theme_combo.setCurrentIndex(2)
        window.request_conversion()
        window.cancel_conversion()
        self.assertEqual(port.projects, ["/tmp/example"])
        self.assertEqual(port.themes[-1], "windows-7")
        self.assertEqual(port.started, 1)
        self.assertEqual(port.cancelled, 1)
        self.assertEqual(window.app_list.count(), 2)
        self.assertFalse(window.start_action.isEnabled())

    def test_offline_error_and_evidence_views_are_visible(self) -> None:
        window = MainWindow()
        window.set_codex_state("auth_required", "Sign in with ChatGPT in Codex before conversion.")
        window.add_agent_event(AgentEvent("warning", "Authentication required", "No credentials shown."))
        window.set_analysis("Multiple frontend applications detected.")
        window.set_verification("Behavior comparison needs review.", result="Review required")
        window.set_diff("M src/App.tsx")
        self.assertIn("Sign in", window.readiness.text())
        self.assertEqual(window.status_phase.text(), "Sign in required")
        self.assertEqual(window.event_list.count(), 1)
        self.assertIn("Multiple", window.analysis_text.toPlainText())
        self.assertIn("M src", window.diff_text.toPlainText())
        self.assertIn("Review", window.result_banner.text())

    def test_installed_gui_has_code_native_theme_preview_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            window = MainWindow(asset_root=Path(temp))
            self.assertIsNotNone(window.preview.pixmap())
            self.assertFalse(window.preview.pixmap().isNull())

    def test_agent_event_view_retains_a_bounded_readable_tail(self) -> None:
        window = MainWindow()
        for identifier in range(525):
            window.add_agent_event(AgentEvent("command", f"event {identifier}", "detail"))
        self.assertEqual(window.event_list.count(), 500)
        self.assertIn("event 25", window.event_list.item(0).text())
        self.assertIn("event 524", window.event_list.item(499).text())

    def test_normal_launch_schedules_an_automatic_codex_readiness_check(self) -> None:
        from retro_web_ui_gui import app as gui_module

        controller = SimpleNamespace(refresh_codex=mock.Mock())
        window = SimpleNamespace(
            controller=controller,
            show=mock.Mock(),
            set_codex_state=mock.Mock(),
        )
        application = SimpleNamespace(exec=mock.Mock(return_value=0))
        with (
            mock.patch.object(gui_module, "create_application", return_value=(application, window)),
            mock.patch("PySide6.QtCore.QTimer.singleShot") as single_shot,
        ):
            self.assertEqual(gui_module.main([]), 0)
        window.set_codex_state.assert_called_once()
        single_shot.assert_called_once_with(0, controller.refresh_codex)


if __name__ == "__main__":
    unittest.main()
