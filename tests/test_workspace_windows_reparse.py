from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from retro_web_ui_gui.workspace import WorkspaceError, WorkspaceStore


@unittest.skipUnless(os.name == "nt", "real Windows junction validation requires Windows")
class WindowsJunctionIntegrationTests(unittest.TestCase):
    """Exercise real NTFS junctions against the production containment path."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.project_root = self.base / "project"
        (self.project_root / "app").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def junction(link: Path, target: Path) -> None:
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            raise unittest.SkipTest(f"real junction creation unavailable: {completed.stderr or completed.stdout}")

    def make_store(self):
        root = self.base / "workspace"
        store = WorkspaceStore(root)
        project = store.open_project(self.project_root)
        session = store.create_session(project.project_id, selected_app="app")
        store.capture_bytes(project.project_id, session.session_id, "baseline.bin", b"baseline")
        return root, store, project, session

    def test_real_junction_replacement_is_rejected_at_every_workspace_directory(self) -> None:
        for boundary in ("root", "projects", "project", "session", "artifacts"):
            with self.subTest(boundary=boundary):
                case = self.base / f"case-{boundary}"
                case.mkdir()
                original_project = self.project_root
                self.project_root = case / "project"
                (self.project_root / "app").mkdir(parents=True)
                root, store, project, session = self.make_store()
                targets = {
                    "root": root,
                    "projects": store.projects_root,
                    "project": store._project_dir(project.project_id),
                    "session": store._session_dir(project.project_id, session.session_id),
                    "artifacts": store._artifact_dir(project.project_id, session.session_id),
                }
                target = targets[boundary]
                intended = store._artifact_dir(project.project_id, session.session_id) / "escape.bin"
                relative_escape = intended.relative_to(target)
                outside = case / f"outside-{boundary}"
                target.rename(outside)
                self.junction(target, outside)
                sentinel = outside / "sentinel.txt"
                sentinel.write_text("unchanged", encoding="utf-8")
                escaped = outside / relative_escape
                try:
                    with self.assertRaises(WorkspaceError):
                        store.capture_bytes(project.project_id, session.session_id, "escape.bin", b"must not escape")
                    self.assertFalse(escaped.exists())
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")
                    with self.assertRaises(WorkspaceError):
                        store.artifact_status(project.project_id, session.session_id, "baseline.bin")
                finally:
                    if target.exists():
                        os.rmdir(target)
                self.project_root = original_project


if __name__ == "__main__":
    unittest.main()
