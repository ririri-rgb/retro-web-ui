from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from retro_web_ui_gui.codex_bridge import BridgeEvent, CodexAvailability
from retro_web_ui_gui.controller import AGENT_RESULT_SCHEMA, CommandRunResult, DesktopController
from retro_web_ui_gui.core_facade import CoreFacade
from retro_web_ui_gui.workflow import ConversionWorkflow, WorkflowState


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "static-html"


class FakeWindow:
    def __init__(self) -> None:
        self.states: list[tuple[str, str]] = []
        self.projects: list[tuple[str, list[dict]]] = []
        self.events: list[dict] = []
        self.verification = ""
        self.diff = ""
        self.allow = True

    def set_codex_state(self, state, message): self.states.append((state, message))
    def set_project(self, root, applications=None): self.projects.append((root, list(applications or [])))
    def set_analysis(self, result): self.analysis = result
    def add_agent_event(self, event): self.events.append(dict(event))
    def request_approval(self, request): self.request = dict(request); return self.allow
    def set_verification(self, text, *, result="Review required"): self.verification = text; self.result = result
    def set_diff(self, text): self.diff = text
    def set_models(self, models, *, account_text="Signed in with ChatGPT"): self.models = list(models); self.account_text = account_text
    def open_external_url(self, url): self.opened_url = url; return True
    def set_busy(self, busy, message=None): self.busy = busy; self.busy_message = message
    def request_user_input(self, request): self.user_input_request = dict(request); return {"choice": ["Safe"]}


class FakeBridge:
    executable = "codex"
    def __init__(self) -> None:
        self.listener = None; self.started = False; self.calls = []; self.approved = []; self.denied = []; self.account_type = "chatgpt"
    def add_listener(self, listener): self.listener = listener; return lambda: None
    def start(self, **kwargs): self.started = True; self.calls.append(("start", kwargs)); return {"capabilities": {}}
    def restart(self, **kwargs): self.started = True; self.calls.append(("restart", kwargs)); return {"capabilities": {}}
    def account_read(self): return {"account": {"type": self.account_type}} if self.account_type else {"account": None}
    def read_configuration(self, **kwargs): self.calls.append(("config", kwargs)); return {"config": {}}
    def list_models(self): return {"data": [{"id": "gpt-5.6-terra"}]}
    def start_thread(self, **kwargs): self.calls.append(("thread", kwargs)); return {"thread": {"id": "thr_1"}}
    def resume_thread(self, thread_id, **kwargs): self.calls.append(("resume", {"thread": thread_id, **kwargs})); return {"thread": {"id": thread_id}}
    def read_thread(self, thread_id, **kwargs): self.calls.append(("read", {"thread": thread_id, **kwargs})); return {"thread": {"id": thread_id, "turns": [{"status": "interrupted"}]}}
    def start_turn(self, thread_id, input_items, **kwargs): self.calls.append(("turn", {"thread": thread_id, "input": list(input_items), **kwargs})); return {"turn": {"id": "turn_1"}}
    def approve(self, request_id): self.approved.append(request_id)
    def deny(self, request_id): self.denied.append(request_id)
    def answer_user_input(self, request_id, answers): self.calls.append(("user_input", {"id": request_id, "answers": answers}))
    def interrupt_turn(self, thread_id, turn_id=None): self.calls.append(("interrupt", {"thread": thread_id, "turn": turn_id}))
    def shutdown(self): self.started = False
    def emit(self, kind, data): self.listener(BridgeEvent(kind, data))


class ControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = FakeWindow(); self.bridge = FakeBridge()
        self.controller = DesktopController(
            self.window, facade=CoreFacade(), bridge=self.bridge,
            availability_detector=lambda: CodexAvailability(True, "codex", "test"),
        )

    def tearDown(self) -> None:
        self.controller.close()

    def test_project_readiness_baseline_and_skill_turn_context(self) -> None:
        self.controller.select_project(str(FIXTURE))
        self.controller.select_theme("windows-98")
        snapshot = self.controller.create_baseline()
        self.addCleanup(lambda: snapshot.baseline and snapshot.baseline.parent.exists() and __import__("shutil").rmtree(snapshot.baseline.parent))
        self.controller.refresh_codex()
        self.assertIn(("config", {"cwd": FIXTURE.resolve()}), self.bridge.calls)
        self.controller.start_conversion(model="gpt-5.6-terra", effort="medium")
        thread = dict(self.bridge.calls)["thread"]
        turn = dict(self.bridge.calls)["turn"]
        self.assertEqual(thread, {"cwd": str(FIXTURE.resolve())})
        self.assertEqual(turn["model"], "gpt-5.6-terra")
        self.assertEqual(turn["cwd"], str(FIXTURE.resolve()))
        self.assertEqual(turn["approvalPolicy"], "on-request")
        self.assertEqual(turn["sandboxPolicy"], {
            "type": "workspaceWrite",
            "writableRoots": [str(FIXTURE.resolve())],
            "networkAccess": False,
        })
        self.assertEqual(turn["outputSchema"], AGENT_RESULT_SCHEMA)
        self.assertEqual(turn["input"][0]["type"], "skill")
        self.assertEqual(turn["input"][0]["name"], "retro-web-ui")
        self.assertIn("$retro-web-ui", turn["input"][1]["text"])
        self.assertIn("behavior_baseline", turn["input"][1]["text"])
        self.assertIn("precomputed_theme_bundle", turn["input"][1]["text"])
        self.assertIn("doctor.python.runnable", turn["input"][1]["text"])

    def test_auth_account_types_are_not_mislabeled_as_chatgpt(self) -> None:
        self.assertTrue(self.controller._requires_login({"account": None}))
        self.assertFalse(self.controller._requires_login({"account": {"type": "chatgpt"}}))
        self.assertEqual(self.controller._account_type({"account": {"type": "apiKey"}}), "apikey")

    def test_missing_codex_diagnostic_is_actionable_and_secret_redacted(self) -> None:
        self.controller.availability_detector = lambda: CodexAvailability(
            False, None, None, "launcher failed with Bearer top-secret-token"
        )
        self.controller.refresh_codex()
        state, message = self.window.states[-1]
        self.assertEqual(state, "unavailable")
        self.assertIn("PATH", message)
        self.assertIn("[REDACTED]", message)
        self.assertNotIn("top-secret-token", message)

    def test_conversion_rechecks_current_chatgpt_auth_before_starting_thread(self) -> None:
        self.controller.select_project(str(FIXTURE))
        self.controller.select_theme("windows-xp")
        snapshot = self.controller.create_baseline()
        self.addCleanup(lambda: snapshot.baseline and snapshot.baseline.parent.exists() and __import__("shutil").rmtree(snapshot.baseline.parent))
        self.controller.refresh_codex()
        self.bridge.account_type = "apiKey"
        with self.assertRaisesRegex(RuntimeError, "ChatGPT Codex session"):
            self.controller.start_conversion()
        self.assertFalse(any(name == "thread" for name, _ in self.bridge.calls))
        self.assertEqual(self.window.states[-1][0], "auth_required")

    def test_turn_start_failure_unlocks_gui_and_preserves_retryable_baseline(self) -> None:
        self.controller.select_project(str(FIXTURE))
        self.controller.select_theme("windows-xp")
        snapshot = self.controller.create_baseline()
        self.addCleanup(lambda: snapshot.baseline and snapshot.baseline.parent.exists() and __import__("shutil").rmtree(snapshot.baseline.parent))
        self.controller.refresh_codex()
        original = self.bridge.start_turn
        self.bridge.start_turn = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("protocol mismatch"))
        self.addCleanup(lambda: setattr(self.bridge, "start_turn", original))
        with self.assertRaisesRegex(RuntimeError, "protocol mismatch"):
            self.controller.start_conversion()
        self.assertEqual(self.controller.workflow.state, WorkflowState.BASELINE_READY)
        self.assertFalse(self.window.busy)
        self.assertEqual(self.window.states[-1][0], "error")

    def test_bridge_approval_is_normalized_and_answered(self) -> None:
        self.bridge.emit("approval_requested", {"approval": {"requestId": 42, "command": ["npm", "run", "build"], "cwd": "/target", "reason": "Build"}})
        self.assertEqual(self.bridge.approved, [42])
        self.assertEqual(self.window.request["command"], "npm run build")
        self.window.allow = False
        self.bridge.emit("approval_requested", {"approval": {"requestId": 43}})
        self.assertEqual(self.bridge.denied, [43])

    def test_permissions_risk_and_tool_user_input_are_not_generic(self) -> None:
        self.bridge.emit("approval_requested", {"approval": {
            "requestId": 52,
            "kind": "permissions",
            "cwd": "/target",
            "details": {"permissions": {"network": {"enabled": True}}},
        }})
        self.assertIn("Additional permissions", self.window.request["risk"])
        self.bridge.emit("user_input_requested", {
            "requestId": "input-1",
            "details": {"questions": [{"id": "choice", "question": "Continue safely?"}]},
        })
        self.assertIn(("user_input", {"id": "input-1", "answers": {"choice": ["Safe"]}}), self.bridge.calls)

    def test_unexpected_exit_can_reconnect_and_resume_durable_thread(self) -> None:
        self.controller.select_project(str(FIXTURE))
        self.controller.thread_id = "thr-recover"
        self.controller.workflow.state = WorkflowState.AGENT_RUNNING
        self.bridge.emit("unexpected_exit", {"reason": "crash"})
        self.controller.reconnect()
        self.assertIn(("resume", {"thread": "thr-recover"}), self.bridge.calls)
        self.assertIn(("read", {"thread": "thr-recover", "include_turns": True}), self.bridge.calls)
        self.assertTrue(any(event.get("kind") == "thread_recovered" for event in self.window.events))
        self.assertEqual(self.window.states[-1][0], "ready")

    def test_completed_turn_for_another_nested_thread_is_ignored(self) -> None:
        self.controller.thread_id = "thr-active"
        self.bridge.emit("turn_completed", {"params": {"turn": {"id": "turn-other", "threadId": "thr-other", "status": "completed"}}})
        self.assertEqual(self.window.verification, "")

    def test_completed_turn_runs_only_allowed_target_plan_then_verifies(self) -> None:
        controller = self.controller
        controller.select_project(str(ROOT))
        controller.select_application("tests/fixtures/react-vite")
        controller.select_theme("japanese-freeware-2000s")
        snapshot = controller.create_baseline()
        self.addCleanup(lambda: snapshot.baseline and snapshot.baseline.parent.exists() and __import__("shutil").rmtree(snapshot.baseline.parent))
        controller.workflow.set_verification_approval(0, True)
        ran = []
        controller.command_runner = lambda plan: (ran.append(plan.argv) or CommandRunResult(plan.identifier, True, "build passed"))
        controller.thread_id = "thr_1"; controller.turn_id = "turn_1"; controller.workflow.begin_agent_conversion()
        self.bridge.emit("turn_completed", {"params": {"threadId": "thr_1", "turn": {"id": "turn_1"}}})
        self.assertEqual(ran, [("npm", "run", "build")])
        self.assertIn("Target command results", self.window.verification)
        self.assertIn(controller.workflow.state, {WorkflowState.REVIEW_REQUIRED, WorkflowState.COMPLETE})

    def test_completed_agent_message_is_readable_and_review_gap_is_not_complete(self) -> None:
        controller = self.controller
        controller.select_project(str(FIXTURE))
        controller.select_theme("windows-xp")
        snapshot = controller.create_baseline()
        self.addCleanup(lambda: snapshot.baseline and snapshot.baseline.parent.exists() and __import__("shutil").rmtree(snapshot.baseline.parent))
        controller.thread_id = "thr_1"; controller.turn_id = "turn_1"; controller.workflow.begin_agent_conversion()
        result = {
            "classification": "complete",
            "summary": "Converted the selected application.",
            "changedFiles": ["index.html", "styles.css"],
            "reviewItems": ["Browser-based visual review was unavailable."],
            "verificationPerformed": ["static audit", "behavior compare"],
            "verificationUnavailable": ["browser runtime"],
        }
        event_count = len(self.window.events)
        self.bridge.emit("agent_message_delta", {"params": {"delta": "noise"}})
        self.assertEqual(len(self.window.events), event_count)
        self.bridge.emit("item_completed", {"params": {"threadId": "thr_1", "turnId": "turn_1", "item": {
            "type": "agentMessage", "phase": "final_answer", "text": __import__("json").dumps(result),
        }}})
        self.assertEqual(self.window.events[-1]["message"], result["summary"])
        self.bridge.emit("turn_completed", {"params": {"threadId": "thr_1", "turn": {"id": "turn_1"}}})
        self.assertEqual(self.window.result, "complete_with_review_items")
        self.assertIn("browser runtime", self.window.verification)

    def test_missing_structured_final_assessment_requires_review(self) -> None:
        controller = self.controller
        controller.select_project(str(FIXTURE))
        controller.select_theme("windows-98")
        snapshot = controller.create_baseline()
        self.addCleanup(lambda: snapshot.baseline and snapshot.baseline.parent.exists() and __import__("shutil").rmtree(snapshot.baseline.parent))
        controller.thread_id = "thr_1"; controller.turn_id = "turn_1"; controller.workflow.begin_agent_conversion()
        self.bridge.emit("item_completed", {"params": {"threadId": "thr_1", "turnId": "turn_1", "item": {
            "type": "agentMessage", "phase": "final_answer", "text": "Converted, but no structured result.",
        }}})
        self.bridge.emit("turn_completed", {"params": {"threadId": "thr_1", "turn": {"id": "turn_1"}}})
        self.assertEqual(self.window.result, "review_required")
        self.assertIn("did not match the required result schema", self.window.verification)

    def test_structured_result_from_another_or_unidentified_turn_is_not_adopted(self) -> None:
        result = {
            "classification": "complete", "summary": "Other result", "changedFiles": [],
            "reviewItems": [], "verificationPerformed": [], "verificationUnavailable": [],
        }
        self.controller.thread_id = "thr-active"; self.controller.turn_id = "turn-active"
        for params in (
            {"item": {"type": "agentMessage", "phase": "final_answer", "text": __import__("json").dumps(result)}},
            {"threadId": "thr-other", "turnId": "turn-other", "item": {"type": "agentMessage", "phase": "final_answer", "text": __import__("json").dumps(result)}},
        ):
            self.bridge.emit("item_completed", {"params": params})
        self.assertIsNone(self.controller._agent_result)
        self.assertTrue(all("not used" in event["message"] for event in self.window.events[-2:]))

    def test_failed_authorized_target_command_is_not_hidden_by_cli_evidence(self) -> None:
        controller = self.controller
        controller.select_project(str(ROOT))
        controller.select_application("tests/fixtures/react-vite")
        controller.select_theme("japanese-freeware-2000s")
        snapshot = controller.create_baseline()
        self.addCleanup(lambda: snapshot.baseline and snapshot.baseline.parent.exists() and __import__("shutil").rmtree(snapshot.baseline.parent))
        controller.workflow.set_verification_approval(0, True)
        controller.command_runner = lambda plan: CommandRunResult(plan.identifier, False, "build failed")
        controller.thread_id = "thr_1"; controller.workflow.begin_agent_conversion()
        self.bridge.emit("turn_completed", {"params": {"threadId": "thr_1", "turn": {"id": "turn_1"}}})
        self.assertEqual(controller.workflow.state, WorkflowState.VERIFICATION_FAILED)
        self.assertEqual(self.window.result, "verification_failed")
