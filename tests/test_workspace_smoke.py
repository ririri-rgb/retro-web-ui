from __future__ import annotations

import os
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
            environment = {"XDG_STATE_HOME": str(state)}
            with mock.patch.dict(os.environ, environment, clear=True), mock.patch("retro_web_ui_gui.workspace.sys.platform", "linux"):
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
