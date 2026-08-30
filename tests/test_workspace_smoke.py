from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from retro_web_ui_gui.workspace import WorkspaceStore
from retro_web_ui_gui.workspace_smoke import create_workspace_lifecycle, inspect_workspace_lifecycle


class WorkspaceLifecycleSmokeTests(unittest.TestCase):
    def test_create_restart_restore_integrity_and_privacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            (project / "app").mkdir(parents=True)
            state = base / "state"
            with mock.patch(
                "retro_web_ui_gui.workspace_smoke.default_workspace_root",
                return_value=state / "retro-web-ui",
            ):
                created = create_workspace_lifecycle(project)
                root = Path(created["workspaceRoot"])
                restarted = WorkspaceStore(root)
                restarted.reconcile_startup()
                restored = inspect_workspace_lifecycle(restarted, project)
            self.assertEqual(created["state"], "running")
            self.assertEqual(restored["state"], "transport_lost")
            self.assertEqual(restored["projectAvailability"], "available")
            self.assertEqual(restored["artifactIntegrity"], "available")
            self.assertEqual(restored["privacyScan"], "clean")
            self.assertEqual(created["artifactSha256"], restored["artifactSha256"])


if __name__ == "__main__":
    unittest.main()
