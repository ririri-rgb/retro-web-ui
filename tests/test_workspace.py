from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import retro_web_ui_gui.workspace as workspace_module

from retro_web_ui_gui.workspace import (
    CorruptRecordError,
    IntegrityState,
    SessionState,
    UnsupportedSchemaError,
    WorkspaceError,
    WorkspaceStore,
    default_workspace_root,
)


class WorkspaceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.project_root = self.base / "project"
        self.project_root.mkdir()
        (self.project_root / "app").mkdir()
        self.store = WorkspaceStore(self.base / "workspace", max_artifact_bytes=128)
        self.project = self.store.open_project(self.project_root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def session(self):
        return self.store.create_session(self.project.project_id, selected_app="app", theme="windows-xp")

    def test_canonical_project_deduplicates_normal_paths_but_rejects_symlink_alias(self) -> None:
        same = self.store.open_project(self.project_root / ".")
        self.assertEqual(same.project_id, self.project.project_id)
        link = self.base / "project-link"
        try:
            link.symlink_to(self.project_root, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaises(WorkspaceError):
            self.store.open_project(link)

    def test_selected_application_rejects_symlink_traversal(self) -> None:
        linked = self.project_root / "linked"
        try:
            linked.symlink_to(self.project_root / "app", target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaises(WorkspaceError):
            self.store.create_session(self.project.project_id, selected_app="linked")

    def test_session_transitions_are_explicit_and_restart_reconciles_active_work(self) -> None:
        session = self.session()
        session = self.store.transition(self.project.project_id, session.session_id, SessionState.PREPARED)
        session = self.store.transition(self.project.project_id, session.session_id, SessionState.RUNNING, thread_id="thr_1", turn_id="turn_1")
        self.assertEqual(session.thread_id, "thr_1")
        restarted = WorkspaceStore(self.base / "workspace")
        recovered = restarted.reconcile_startup()
        self.assertEqual([item.session_id for item in recovered], [session.session_id])
        recovered_session = restarted.get_session(self.project.project_id, session.session_id)
        self.assertEqual(recovered_session.state, SessionState.TRANSPORT_LOST)
        self.assertIn("stopped", recovered_session.recovery_reason or "")
        with self.assertRaises(WorkspaceError):
            restarted.transition(self.project.project_id, session.session_id, SessionState.VERIFYING)

    def test_extended_lifecycle_metadata_and_terminal_timestamps(self) -> None:
        session = self.store.create_session(self.project.project_id, selected_app="app", model="gpt-5", reasoning_effort="high")
        session = self.store.transition(self.project.project_id, session.session_id, SessionState.PREPARED)
        session = self.store.transition(self.project.project_id, session.session_id, SessionState.AWAITING_APPROVAL)
        session = self.store.transition(self.project.project_id, session.session_id, SessionState.RUNNING, thread_id="thr", turn_id="turn")
        self.assertIsNotNone(session.started_at)
        session = self.store.transition(self.project.project_id, session.session_id, SessionState.VERIFICATION_PENDING)
        session = self.store.transition(self.project.project_id, session.session_id, SessionState.VERIFYING)
        session = self.store.transition(self.project.project_id, session.session_id, SessionState.COMPLETE_WITH_REVIEW_ITEMS, classification="complete_with_review_items")
        self.assertEqual(session.model, "gpt-5")
        self.assertEqual(session.reasoning_effort, "high")
        self.assertIsNotNone(session.ended_at)

    def test_list_issues_surfaces_corrupt_and_newer_records(self) -> None:
        session = self.session()
        path = self.store._session_dir(self.project.project_id, session.session_id) / "session.json"
        path.write_text("{", encoding="utf-8")
        issues = self.store.list_issues()
        self.assertEqual(issues[0]["kind"], "session_record")
        self.assertIn("Unreadable", issues[0]["error"])

    def test_capture_bytes_json_privacy_and_default_root(self) -> None:
        session = self.store.create_session(
            self.project.project_id,
            selected_app="app",
            model="gpt-5.6-terra",
            reasoning_effort="medium",
        )
        self.assertEqual(self.store.capture_bytes(self.project.project_id, session.session_id, "raw.bin", b"ok").integrity, IntegrityState.AVAILABLE)
        self.assertEqual(self.store.capture_json(self.project.project_id, session.session_id, "result.json", {"result": [1]}).integrity, IntegrityState.AVAILABLE)
        with self.assertRaises(WorkspaceError):
            self.store.capture_json(self.project.project_id, session.session_id, "unsafe.json", {"token": "no"})
        persisted = self.store.get_session(self.project.project_id, session.session_id)
        self.assertEqual((persisted.model, persisted.reasoning_effort), ("gpt-5.6-terra", "medium"))
        self.assertIn("Retro Web UI" if os.name == "nt" or __import__("sys").platform == "darwin" else "retro-web-ui", str(default_workspace_root()))

    @unittest.skipIf(os.name == "nt", "POSIX mode assertions do not apply on Windows")
    def test_workspace_files_are_private_on_posix(self) -> None:
        session = self.session()
        project_dir = self.store._project_dir(self.project.project_id)
        session_json = self.store._session_dir(self.project.project_id, session.session_id) / "session.json"
        self.assertEqual(project_dir.stat().st_mode & 0o777, 0o700)
        self.assertEqual(session_json.stat().st_mode & 0o777, 0o600)

    def test_missing_project_and_selected_application_are_reported_without_deleting_history(self) -> None:
        session = self.session()
        self.assertEqual(self.store.project_availability(self.project.project_id, session.session_id), "available")
        (self.project_root / "app").rmdir()
        self.assertEqual(self.store.project_availability(self.project.project_id, session.session_id), "app_missing")
        self.assertEqual(self.store.get_session(self.project.project_id, session.session_id).session_id, session.session_id)

    def test_capture_hashes_artifact_and_detects_missing_or_tampered_copy(self) -> None:
        session = self.session()
        source = self.base / "evidence.json"
        source.write_bytes(b'{"ok":true}')
        status = self.store.capture_artifact(self.project.project_id, session.session_id, "baseline.json", source)
        self.assertEqual(status.integrity, IntegrityState.AVAILABLE)
        destination = Path(status.path or "")
        destination.write_bytes(b"tampered")
        self.assertEqual(self.store.artifact_status(self.project.project_id, session.session_id, "baseline.json").integrity, IntegrityState.CHANGED)
        destination.unlink()
        self.assertEqual(self.store.artifact_status(self.project.project_id, session.session_id, "baseline.json").integrity, IntegrityState.MISSING)
        self.assertEqual(self.store.artifact_status(self.project.project_id, session.session_id, "other.json").integrity, IntegrityState.NOT_CAPTURED)
        self.assertEqual(self.store.mark_artifact_not_applicable(self.project.project_id, session.session_id, "before.png").integrity, IntegrityState.NOT_APPLICABLE)

    def test_artifact_source_is_confined_sized_and_rejects_traversal_manifest(self) -> None:
        session = self.session()
        source = self.project_root / "app" / "proof.txt"
        source.write_text("proof", encoding="utf-8")
        with self.assertRaises(WorkspaceError):
            self.store.capture_artifact(self.project.project_id, session.session_id, "proof.txt", source, allowed_root=self.base / "elsewhere")
        too_large = self.base / "large.txt"; too_large.write_bytes(b"x" * 129)
        with self.assertRaises(WorkspaceError):
            self.store.capture_artifact(self.project.project_id, session.session_id, "large.txt", too_large)
        self.store.capture_artifact(self.project.project_id, session.session_id, "proof.txt", source, allowed_root=self.project_root)
        manifest = self.store._session_dir(self.project.project_id, session.session_id) / "session.json"
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        doc["record"]["artifacts"]["proof.txt"]["path"] = "../../project.json"
        manifest.write_text(json.dumps(doc), encoding="utf-8")
        status = self.store.artifact_status(self.project.project_id, session.session_id, "proof.txt")
        self.assertEqual(status.integrity, IntegrityState.MISSING)
        self.assertIn("manifest", status.reason or "")

    def test_corrupt_partial_and_unknown_schema_records_are_isolated(self) -> None:
        session = self.session()
        path = self.store._session_dir(self.project.project_id, session.session_id) / "session.json"
        path.write_text("{", encoding="utf-8")
        with self.assertRaises(CorruptRecordError):
            self.store.get_session(self.project.project_id, session.session_id)
        self.assertEqual(self.store.list_sessions(self.project.project_id), [])
        other = self.session()
        path = self.store._session_dir(self.project.project_id, other.session_id) / "session.json"
        doc = json.loads(path.read_text(encoding="utf-8")); doc["schemaVersion"] = 99
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(UnsupportedSchemaError):
            self.store.get_session(self.project.project_id, other.session_id)

    def test_comparison_tolerates_incomplete_artifacts(self) -> None:
        left, right = self.session(), self.session()
        first, second = self.base / "one.txt", self.base / "two.txt"
        first.write_text("one", encoding="utf-8"); second.write_text("two", encoding="utf-8")
        self.store.capture_artifact(self.project.project_id, left.session_id, "same.txt", first)
        self.store.capture_artifact(self.project.project_id, right.session_id, "same.txt", first)
        self.store.capture_artifact(self.project.project_id, left.session_id, "different.txt", first)
        self.store.capture_artifact(self.project.project_id, right.session_id, "different.txt", second)
        report = self.store.compare_sessions(self.project.project_id, left.session_id, right.session_id)
        self.assertEqual(report["artifacts"]["same.txt"]["outcome"], "same")
        self.assertEqual(report["artifacts"]["different.txt"]["outcome"], "different")
        Path(self.store.artifact_status(self.project.project_id, right.session_id, "same.txt").path or "").unlink()
        report = self.store.compare_sessions(self.project.project_id, left.session_id, right.session_id)
        self.assertEqual(report["artifacts"]["same.txt"]["outcome"], "incomplete")

    def test_persistence_has_no_event_or_sensitive_payload_surface(self) -> None:
        session = self.session()
        path = self.store._session_dir(self.project.project_id, session.session_id) / "session.json"
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("event", text.lower())
        with self.assertRaises(WorkspaceError):
            self.store.transition(self.project.project_id, session.session_id, SessionState.PREPARED, thread_id="x" * 2000)

    def test_record_ids_and_symlinked_workspace_children_are_rejected(self) -> None:
        with self.assertRaises(WorkspaceError):
            self.store.get_project("../outside")
        session = self.session()
        path = self.store._session_dir(self.project.project_id, session.session_id) / "session.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["record"]["session_id"] = "00000000-0000-0000-0000-000000000000"
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(CorruptRecordError):
            self.store.get_session(self.project.project_id, session.session_id)
        link_root = self.base / "linked-workspace"
        try:
            link_root.symlink_to(self.base / "workspace", target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaises(WorkspaceError):
            WorkspaceStore(link_root)

    def test_initialized_storage_anchor_rejects_root_replacement_before_outside_write(self) -> None:
        session = self.session()
        workspace_root = self.base / "workspace"
        outside = self.base / "outside-workspace"
        workspace_root.rename(outside)
        try:
            workspace_root.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaisesRegex(WorkspaceError, "symlink|identity"):
            self.store.capture_bytes(self.project.project_id, session.session_id, "escape.bin", b"no escape")
        escaped = outside / "projects" / self.project.project_id / "sessions" / session.session_id / "artifacts" / "escape.bin"
        self.assertFalse(escaped.exists())

    def test_final_record_symlink_is_rejected_without_loading_external_json(self) -> None:
        session = self.session()
        record = self.store._session_dir(self.project.project_id, session.session_id) / "session.json"
        outside = self.base / "outside-session.json"
        outside.write_bytes(record.read_bytes())
        record.unlink()
        try:
            record.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaises(CorruptRecordError):
            self.store.get_session(self.project.project_id, session.session_id)

    def test_integrity_check_rejects_oversized_post_capture_replacement_without_reading_it(self) -> None:
        session = self.session()
        self.store.capture_bytes(self.project.project_id, session.session_id, "bounded.bin", b"ok")
        status = self.store.artifact_status(self.project.project_id, session.session_id, "bounded.bin")
        Path(status.path or "").write_bytes(b"x" * 10_000)
        changed = self.store.artifact_status(self.project.project_id, session.session_id, "bounded.bin")
        self.assertEqual(changed.integrity, IntegrityState.CHANGED)
        self.assertIn("size", changed.reason or "")

    def test_equal_content_artifact_symlink_is_never_accepted_as_available(self) -> None:
        session = self.session()
        first = self.store.capture_bytes(self.project.project_id, session.session_id, "first.bin", b"same")
        second = self.store.capture_bytes(self.project.project_id, session.session_id, "second.bin", b"same")
        second_path = Path(second.path or "")
        second_path.unlink()
        try:
            second_path.symlink_to(Path(first.path or ""))
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        status = self.store.artifact_status(self.project.project_id, session.session_id, "second.bin")
        self.assertNotEqual(status.integrity, IntegrityState.AVAILABLE)
        self.assertIn("symlink", status.reason or "")

    def test_corrupt_sessions_still_count_toward_retention_limit(self) -> None:
        session = self.session()
        path = self.store._session_dir(self.project.project_id, session.session_id) / "session.json"
        path.write_text("{", encoding="utf-8")
        self.assertEqual(self.store.list_sessions(self.project.project_id), [])
        with mock.patch("retro_web_ui_gui.workspace.MAX_SESSIONS_PER_PROJECT", 1):
            with self.assertRaisesRegex(WorkspaceError, "limit"):
                self.session()

    def test_credential_shaped_prose_is_redacted_before_persistence(self) -> None:
        store = WorkspaceStore(self.base / "privacy-workspace", max_artifact_bytes=2_048)
        project = store.open_project(self.project_root)
        session = store.create_session(project.project_id, selected_app="app")
        value = {
            "summary": (
                "Cookie: session=secret-cookie\n"
                "Authorization: Basic secret-basic\n"
                "Proxy-Authorization: Digest secret-digest\n"
                "API key: secret-api\n"
                "device code: ABCD-EFGH\n"
                "https://example.test/login/device?access_token=secret-query"
            ),
            "details": (
                "-----BEGIN PRIVATE KEY-----\nsecret-key\n-----END PRIVATE KEY-----\n"
                "https://user:secret-password@example.test/callback"
            ),
        }
        status = store.capture_json(project.project_id, session.session_id, "assessment.json", value)
        text = Path(status.path or "").read_text(encoding="utf-8")
        for secret in (
            "secret-cookie", "secret-basic", "secret-digest", "secret-api",
            "ABCD-EFGH", "secret-query", "secret-key", "secret-password",
        ):
            self.assertNotIn(secret, text)
        self.assertIn("REDACTED", text)

    def test_artifact_names_are_portable_across_case_insensitive_filesystems(self) -> None:
        session = self.session()
        self.store.capture_bytes(self.project.project_id, session.session_id, "Evidence.json", b"one")
        with self.assertRaisesRegex(WorkspaceError, "portable case"):
            self.store.capture_bytes(self.project.project_id, session.session_id, "evidence.json", b"two")
        for name in ("CON", "nul.txt", "trailing."):
            with self.subTest(name=name), self.assertRaises(WorkspaceError):
                self.store.capture_bytes(self.project.project_id, session.session_id, name, b"invalid")

    def test_windows_reparse_attribute_is_treated_as_link_like(self) -> None:
        path = mock.Mock()
        path.lstat.return_value = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
        )
        self.assertTrue(workspace_module._is_link_like(path))

    def test_directory_fsync_unsupported_after_replace_is_best_effort(self) -> None:
        destination = self.base / "atomic" / "value.bin"
        with mock.patch("retro_web_ui_gui.workspace.os.fsync", side_effect=[None, OSError("unsupported")]):
            WorkspaceStore._atomic_bytes(destination, b"durable enough")
        self.assertEqual(destination.read_bytes(), b"durable enough")

    def test_default_workspace_root_platform_and_environment_precedence(self) -> None:
        decide = workspace_module._workspace_root_for
        home = Path("/users/test")
        self.assertEqual(decide("nt", "win32", {"LOCALAPPDATA": "/win/local", "APPDATA": "/win/roaming"}, home), Path("/win/local/Retro Web UI"))
        self.assertEqual(decide("nt", "win32", {"APPDATA": "/win/roaming"}, home), Path("/win/roaming/Retro Web UI"))
        self.assertEqual(decide("nt", "win32", {}, home), Path("/users/test/AppData/Local/Retro Web UI"))
        self.assertEqual(decide("posix", "darwin", {}, home), Path("/users/test/Library/Application Support/Retro Web UI"))
        self.assertEqual(decide("posix", "linux", {"XDG_STATE_HOME": "/xdg/state", "XDG_DATA_HOME": "/xdg/data"}, home), Path("/xdg/state/retro-web-ui"))
        self.assertEqual(decide("posix", "linux", {"XDG_DATA_HOME": "/xdg/data"}, home), Path("/xdg/data/retro-web-ui"))
        self.assertEqual(decide("posix", "linux", {}, home), Path("/users/test/.local/state/retro-web-ui"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
