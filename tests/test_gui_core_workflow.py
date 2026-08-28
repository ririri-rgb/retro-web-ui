from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path

from retro_web_ui_gui.core_facade import CoreFacade, ScopeError
from retro_web_ui_gui.workflow import ConversionWorkflow, ResultClassification, WorkflowState


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class CoreFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.facade = CoreFacade()

    def test_info_uses_bundled_cli_contract(self) -> None:
        response = self.facade.info()
        self.assertEqual(response.status, "ok")
        self.assertTrue(response.result["manifest_compatible"])
        self.assertEqual(response.document["schema_version"], 1)
        self.assertTrue(self.facade.skill_path.is_file())

    def test_explicit_cli_path_retains_process_isolation_route(self) -> None:
        facade = CoreFacade(cli_path=ROOT / "skills" / "retro-web-ui" / "scripts" / "retro_web_ui.py")
        response = facade.info()
        self.assertEqual(response.status, "ok")
        self.assertEqual(facade.skill_path, ROOT / "skills" / "retro-web-ui" / "SKILL.md")

    def test_snapshot_is_external_and_compare_is_unchanged(self) -> None:
        target = FIXTURES / "static-html"
        baseline, response = self.facade.create_external_baseline(target)
        self.addCleanup(lambda: baseline.parent.exists() and __import__("shutil").rmtree(baseline.parent))
        self.assertTrue(baseline.is_file())
        self.assertNotIn(str(target.resolve()), str(baseline))
        self.assertEqual(response.status, "ok")
        self.assertEqual(self.facade.compare(baseline, target).result["status"], "unchanged")

    def test_scope_rejects_symlink_and_outside_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            root.mkdir()
            outside = Path(temp) / "outside"
            outside.mkdir()
            link = root / "linked"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlinks unavailable: {error}")
            with self.assertRaises(ScopeError):
                self.facade.contained_path(root, link, require_directory=True)
            with self.assertRaises(ScopeError):
                self.facade.contained_path(root, outside, require_directory=True)

    def test_verification_command_requires_authorization_and_no_shell(self) -> None:
        target = FIXTURES / "static-html"
        with self.assertRaises(PermissionError):
            self.facade.run_verification_command(target, target, [sys.executable, "-c", "print('ok')"], authorized=False)
        result = self.facade.run_verification_command(
            target,
            target,
            [sys.executable, "-c", "print('verified')"],
            authorized=True,
            timeout_seconds=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "verified")


class WorkflowTests(unittest.TestCase):
    def test_long_running_dev_and_serve_scripts_are_not_verification_commands(self) -> None:
        self.assertTrue(ConversionWorkflow._finite_verification_purpose("build"))
        self.assertTrue(ConversionWorkflow._finite_verification_purpose("typecheck"))
        self.assertFalse(ConversionWorkflow._finite_verification_purpose("dev"))
        self.assertFalse(ConversionWorkflow._finite_verification_purpose("serve"))
        self.assertFalse(ConversionWorkflow._finite_verification_purpose("watch"))

    def test_monorepo_requires_explicit_application_then_exposes_approval_plan(self) -> None:
        workflow = ConversionWorkflow(CoreFacade())
        first = workflow.prepare(ROOT)
        self.assertEqual(first.state, WorkflowState.APP_SELECTION_REQUIRED)
        ready = workflow.select_application("tests/fixtures/react-vite")
        self.assertEqual(ready.state, WorkflowState.READY_FOR_BASELINE)
        self.assertTrue(ready.approvals)
        self.assertEqual(ready.approvals[0].working_directory, (FIXTURES / "react-vite").resolve())
        changed = workflow.set_verification_approval(ready.approvals[0].identifier, True)
        self.assertEqual(changed.approvals[0].status, "allowed")

    def test_baseline_and_unchanged_behavior_can_complete_deterministic_checks(self) -> None:
        workflow = ConversionWorkflow(CoreFacade())
        workflow.prepare(FIXTURES / "static-html")
        workflow.select_theme("windows-98")
        baseline = workflow.create_baseline()
        self.addCleanup(lambda: baseline.baseline and baseline.baseline.parent.exists() and __import__("shutil").rmtree(baseline.baseline.parent))
        self.assertEqual(baseline.state, WorkflowState.BASELINE_READY)
        workflow.begin_agent_conversion()
        result = workflow.verify()
        self.assertEqual(result.state, WorkflowState.COMPLETE)
        self.assertEqual(result.classification, ResultClassification.COMPLETE)

    def test_confirmed_behavior_failure_has_explicit_classification(self) -> None:
        workflow = ConversionWorkflow(CoreFacade())
        result = workflow.mark_behavior_incompatible([{"code": "RUNTIME_REGRESSION"}])
        self.assertEqual(result.state, WorkflowState.BEHAVIOR_INCOMPATIBILITY)
        self.assertEqual(result.classification, ResultClassification.BEHAVIOR_INCOMPATIBILITY)
