from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from typing import Any

_BRIDGE_PATH = Path(__file__).resolve().parents[1] / "retro_web_ui_gui" / "codex_bridge.py"
_SPEC = importlib.util.spec_from_file_location("retro_web_ui_gui.codex_bridge", _BRIDGE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

BridgeProtocolError = _MODULE.BridgeProtocolError
BridgeState = _MODULE.BridgeState
BridgeUnavailableError = _MODULE.BridgeUnavailableError
CodexBridge = _MODULE.CodexBridge
redact_secrets = _MODULE.redact_secrets

"""Imports above intentionally bypass the GUI package initializer.

The bridge is stdlib-only and must remain testable when an optional desktop
toolkit is not installed.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from retro_web_ui_gui.codex_bridge import (
    BridgeProtocolError,
    BridgeState,
    BridgeUnavailableError,
    CodexBridge,
    redact_secrets,
    )


class _Input:
    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []
        self.closed = False

    def write(self, value: str) -> int:
        self.writes.append(json.loads(value))
        return len(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _Output:
    def __init__(self) -> None:
        self._queue: "queue.Queue[str]"
        import queue

        self._queue = queue.Queue()

    def emit(self, message: dict[str, Any]) -> None:
        self._queue.put(json.dumps(message) + "\n")

    def close(self) -> None:
        self._queue.put("")

    def readline(self) -> str:
        return self._queue.get()


class _FakeProcess:
    def __init__(self) -> None:
        self.stdin = _Input()
        self.stdout = _Output()
        self.stderr = _Output()
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


class CodexBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.process = _FakeProcess()
        self.bridge = CodexBridge(
            executable=sys.executable,
            process_factory=lambda *args, **kwargs: self.process,
        )

    def tearDown(self) -> None:
        self.bridge.shutdown(wait_seconds=0)

    def _wait_for_write(self, method: str) -> dict[str, Any]:
        for _ in range(100):
            for message in self.process.stdin.writes:
                if message.get("method") == method:
                    return message
            time.sleep(0.005)
        self.fail(f"did not write {method}")

    def _start(self) -> None:
        thread = threading.Thread(target=self.bridge.start)
        thread.start()
        initialize = self._wait_for_write("initialize")
        self.process.stdout.emit({"id": initialize["id"], "result": {"platformOs": "macos"}})
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.bridge.state, BridgeState.READY)
        self.assertIn({"method": "initialized", "params": {}}, self.process.stdin.writes)

    def _request_in_thread(self, callback):
        result: dict[str, Any] = {}

        def run() -> None:
            try:
                result["value"] = callback()
            except Exception as error:  # pragma: no cover - asserted by callers when needed
                result["error"] = error

        thread = threading.Thread(target=run)
        thread.start()
        return thread, result

    def test_initialize_account_models_and_request_correlation(self):
        self._start()
        thread, account = self._request_in_thread(self.bridge.account_read)
        request = self._wait_for_write("account/read")
        self.process.stdout.emit({"id": request["id"], "result": {"account": {"type": "chatgpt"}, "requiresOpenaiAuth": True}})
        thread.join(1)
        self.assertEqual(account["value"]["account"]["type"], "chatgpt")

        thread, models = self._request_in_thread(self.bridge.list_models)
        request = self._wait_for_write("model/list")
        self.process.stdout.emit({"id": request["id"], "result": {"data": [{"id": "gpt-5.6-terra"}]}})
        thread.join(1)
        self.assertEqual(models["value"]["data"][0]["id"], "gpt-5.6-terra")

        config_cwd = Path.cwd().resolve()
        thread, config = self._request_in_thread(lambda: self.bridge.read_configuration(cwd=config_cwd))
        request = self._wait_for_write("config/read")
        self.assertEqual(request["params"], {"cwd": str(config_cwd), "includeLayers": False})
        self.process.stdout.emit({"id": request["id"], "result": {"config": {"model": "gpt-5.6-terra"}}})
        thread.join(1)
        self.assertEqual(config["value"]["config"]["model"], "gpt-5.6-terra")

    def test_start_resolves_platform_launcher_before_spawning(self):
        process = _FakeProcess()
        launched: list[list[str]] = []

        def factory(argv, **kwargs):
            launched.append(argv)
            return process

        with tempfile.TemporaryDirectory() as temporary:
            resolved = Path(temporary) / ("codex.cmd" if os.name == "nt" else "codex")
            resolved.write_bytes(b"launcher")
            resolved.chmod(0o755)
            bridge = CodexBridge(process_factory=factory)
            try:
                with mock.patch.object(_MODULE.shutil, "which", return_value=str(resolved)):
                    thread, result = self._request_in_thread(bridge.start)
                    for _ in range(100):
                        if process.stdin.writes:
                            break
                        time.sleep(0.005)
                    initialize = next(item for item in process.stdin.writes if item.get("method") == "initialize")
                    process.stdout.emit({"id": initialize["id"], "result": {}})
                    thread.join(1)
                self.assertNotIn("error", result)
                self.assertEqual(launched[0], [str(resolved.resolve()), "app-server"])
            finally:
                bridge.shutdown(wait_seconds=0)

    def test_finder_style_launch_uses_bounded_fallback_when_path_has_no_codex(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "ChatGPT.app" / "Contents" / "Resources" / "codex"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"launcher")
            candidate.chmod(0o755)
            with (
                mock.patch.object(_MODULE.shutil, "which", return_value=None),
                mock.patch.object(CodexBridge, "fallback_executable_candidates", return_value=(candidate,)),
            ):
                self.assertEqual(CodexBridge.resolve_executable("codex"), str(candidate.resolve()))

    def test_bare_codex_name_does_not_execute_project_local_shadow(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            shadow = project / ("codex.cmd" if os.name == "nt" else "codex")
            shadow.write_text("@exit /b 0\n" if os.name == "nt" else "#!/bin/sh\nexit 0\n", encoding="utf-8")
            shadow.chmod(0o755)
            original = Path.cwd()
            try:
                os.chdir(project)
                for unsafe_path in ("", ".", os.pathsep.join((".", str(project))), str(project)):
                    with (
                        self.subTest(path=unsafe_path),
                        mock.patch.dict(_MODULE.os.environ, {"PATH": unsafe_path}),
                        mock.patch.object(CodexBridge, "fallback_executable_candidates", return_value=()),
                    ):
                        self.assertIsNone(CodexBridge.resolve_executable("codex"))
            finally:
                os.chdir(original)

    def test_path_search_excludes_empty_dot_and_relative_entries(self):
        absolute = str(Path(tempfile.gettempdir()).resolve())
        unsafe_path = os.pathsep.join(("", ".", "relative-bin", absolute))
        with (
            mock.patch.dict(_MODULE.os.environ, {"PATH": unsafe_path}),
            mock.patch.object(_MODULE.shutil, "which", return_value=None) as which,
            mock.patch.object(CodexBridge, "fallback_executable_candidates", return_value=()),
        ):
            self.assertIsNone(CodexBridge.resolve_executable("codex"))
        self.assertEqual(which.call_args.kwargs["path"], absolute)

    def test_relative_explicit_launcher_is_rejected(self):
        with mock.patch.object(_MODULE.shutil, "which") as which:
            self.assertIsNone(CodexBridge.resolve_executable("./codex"))
        which.assert_not_called()

    def test_start_fails_closed_without_spawning_rejected_project_launcher(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            shadow = project / ("codex.cmd" if os.name == "nt" else "codex")
            shadow.write_bytes(b"untrusted")
            shadow.chmod(0o755)
            factory = mock.Mock()
            bridge = CodexBridge(process_factory=factory)
            with (
                mock.patch.object(_MODULE.shutil, "which", return_value=str(shadow)),
                mock.patch.object(CodexBridge, "fallback_executable_candidates", return_value=()),
                self.assertRaises(BridgeUnavailableError),
            ):
                bridge.start(cwd=project)
            factory.assert_not_called()
            self.assertEqual(bridge.state, BridgeState.EXITED)

    def test_windows_fallback_includes_default_npm_shim(self):
        with tempfile.TemporaryDirectory() as temporary:
            roaming = Path(temporary) / "Roaming"
            local = Path(temporary) / "Local"
            with (
                mock.patch.object(_MODULE.sys, "platform", "win32"),
                mock.patch.dict(
                    _MODULE.os.environ,
                    {"APPDATA": str(roaming), "LOCALAPPDATA": str(local)},
                ),
            ):
                candidates = CodexBridge.fallback_executable_candidates()
            self.assertEqual(candidates[0], roaming / "npm" / "codex.cmd")
            self.assertIn(local / "Programs" / "ChatGPT" / "resources" / "codex.exe", candidates)

    def test_windows_npm_fallback_is_resolved_and_spawned_as_absolute_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            roaming = Path(temporary) / "Roaming"
            candidate = roaming / "npm" / "codex.cmd"
            candidate.parent.mkdir(parents=True)
            candidate.write_text("@exit /b 0\n", encoding="utf-8")
            candidate.chmod(0o755)
            process = _FakeProcess()
            factory = mock.Mock(return_value=process)
            bridge = CodexBridge(process_factory=factory)
            try:
                with (
                    mock.patch.object(_MODULE.sys, "platform", "win32"),
                    mock.patch.dict(
                        _MODULE.os.environ,
                        {"APPDATA": str(roaming), "LOCALAPPDATA": str(Path(temporary) / "Local")},
                    ),
                    mock.patch.object(_MODULE.shutil, "which", return_value=None),
                ):
                    thread, result = self._request_in_thread(bridge.start)
                    for _ in range(100):
                        if process.stdin.writes:
                            break
                        time.sleep(0.005)
                    initialize = next(item for item in process.stdin.writes if item.get("method") == "initialize")
                    process.stdout.emit({"id": initialize["id"], "result": {}})
                    thread.join(1)
                self.assertNotIn("error", result)
                self.assertEqual(factory.call_args.args[0], [str(candidate.resolve()), "app-server"])
            finally:
                bridge.shutdown(wait_seconds=0)

    def test_thread_turn_steer_interrupt_and_diff_events(self):
        self._start()
        thread, holder = self._request_in_thread(lambda: self.bridge.start_thread(cwd="/project"))
        request = self._wait_for_write("thread/start")
        self.process.stdout.emit({"id": request["id"], "result": {"thread": {"id": "thr_1"}}})
        thread.join(1)
        self.assertEqual(holder["value"]["thread"]["id"], "thr_1")

        thread, holder = self._request_in_thread(lambda: self.bridge.start_turn("thr_1", [{"type": "text", "text": "convert"}]))
        request = self._wait_for_write("turn/start")
        self.process.stdout.emit({"id": request["id"], "result": {"turn": {"id": "turn_1", "status": "inProgress"}}})
        thread.join(1)
        self.process.stdout.emit({"method": "turn/diff/updated", "params": {"threadId": "thr_1", "turnId": "turn_1", "diff": "@@ -1 +1 @@"}})
        for _ in range(100):
            if self.bridge.latest_diff("thr_1", "turn_1"):
                break
            time.sleep(0.005)
        self.assertEqual(self.bridge.latest_diff("thr_1", "turn_1"), "@@ -1 +1 @@")

        thread, holder = self._request_in_thread(lambda: self.bridge.steer_turn("thr_1", "turn_1", [{"type": "text", "text": "focus"}]))
        request = self._wait_for_write("turn/steer")
        self.assertEqual(request["params"]["expectedTurnId"], "turn_1")
        self.process.stdout.emit({"id": request["id"], "result": {"turnId": "turn_1"}})
        thread.join(1)

        thread, holder = self._request_in_thread(lambda: self.bridge.interrupt_turn("thr_1"))
        request = self._wait_for_write("turn/interrupt")
        self.process.stdout.emit({"id": request["id"], "result": {}})
        thread.join(1)
        self.assertNotIn("error", holder)

    def test_thread_read_requests_durable_turn_history(self):
        self._start()
        thread, holder = self._request_in_thread(lambda: self.bridge.read_thread("thr_1"))
        request = self._wait_for_write("thread/read")
        self.assertEqual(request["params"], {"threadId": "thr_1", "includeTurns": True})
        self.process.stdout.emit({"id": request["id"], "result": {"thread": {"id": "thr_1", "turns": []}}})
        thread.join(1)
        self.assertEqual(holder["value"]["thread"]["id"], "thr_1")

    def test_server_approval_accept_and_deny_are_json_rpc_responses(self):
        self._start()
        self.process.stdout.emit({
            "id": 90,
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thr", "turnId": "turn", "itemId": "item", "command": "npm run build", "cwd": "/project", "reason": "Verify"},
        })
        for _ in range(100):
            if self.bridge.pending_approvals:
                break
            time.sleep(0.005)
        approval = self.bridge.pending_approvals[0]
        self.assertEqual(approval.kind, "command")
        self.assertEqual(approval.command, ("npm run build",))
        self.bridge.approve(90, for_session=True)
        self.assertIn({"id": 90, "result": {"decision": "acceptForSession"}}, self.process.stdin.writes)

        self.process.stdout.emit({"id": 91, "method": "item/fileChange/requestApproval", "params": {"threadId": "thr", "itemId": "edit"}})
        for _ in range(100):
            if self.bridge.pending_approvals:
                break
            time.sleep(0.005)
        self.bridge.deny(91)
        self.assertIn({"id": 91, "result": {"decision": "decline"}}, self.process.stdin.writes)

        self.process.stdout.emit({
            "id": "permissions-1",
            "method": "item/permissions/requestApproval",
            "params": {
                "threadId": "thr", "turnId": "turn", "itemId": "permissions",
                "cwd": "/project", "permissions": {"network": {"enabled": True}},
            },
        })
        for _ in range(100):
            if any(item.request_id == "permissions-1" for item in self.bridge.pending_approvals):
                break
            time.sleep(0.005)
        permission = next(item for item in self.bridge.pending_approvals if item.request_id == "permissions-1")
        self.assertEqual(permission.kind, "permissions")
        self.bridge.deny("permissions-1")
        self.assertIn({"id": "permissions-1", "result": {"permissions": {}, "scope": "turn"}}, self.process.stdin.writes)

        self.process.stdout.emit({
            "id": "input-1",
            "method": "item/tool/requestUserInput",
            "params": {"threadId": "thr", "turnId": "turn", "itemId": "question", "questions": [{"id": "choice"}]},
        })
        for _ in range(100):
            if any(item.request_id == "input-1" for item in self.bridge.pending_approvals):
                break
            time.sleep(0.005)
        self.bridge.answer_user_input("input-1", {"choice": ["Safe"]})
        self.assertIn({"id": "input-1", "result": {"answers": {"choice": {"answers": ["Safe"]}}}}, self.process.stdin.writes)

    def test_string_server_request_id_and_notification_only_turn_are_supported(self):
        self._start()
        self.process.stdout.emit({
            "id": "approval-77",
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thr-resumed", "itemId": "item"},
        })
        self.process.stdout.emit({
            "method": "turn/started",
            "params": {"threadId": "thr-resumed", "turn": {"id": "turn-resumed", "status": "inProgress", "items": []}},
        })
        for _ in range(100):
            if self.bridge.pending_approvals and any(event.kind == "turn_started" for event in self.bridge.events):
                break
            time.sleep(0.005)
        self.assertEqual(self.bridge.pending_approvals[0].request_id, "approval-77")
        self.bridge.approve("approval-77")
        self.assertIn({"id": "approval-77", "result": {"decision": "accept"}}, self.process.stdin.writes)

        thread, holder = self._request_in_thread(lambda: self.bridge.interrupt_turn("thr-resumed"))
        request = self._wait_for_write("turn/interrupt")
        self.assertEqual(request["params"], {"threadId": "thr-resumed", "turnId": "turn-resumed"})
        self.process.stdout.emit({"id": request["id"], "result": {}})
        thread.join(1)
        self.assertNotIn("error", holder)

    def test_unknown_server_request_is_rejected_instead_of_left_pending(self):
        self._start()
        self.process.stdout.emit({
            "id": "dynamic-tool-1",
            "method": "item/tool/call",
            "params": {"name": "unsupported-client-tool", "accessToken": "secret"},
        })
        for _ in range(100):
            if any(event.kind == "server_request" for event in self.bridge.events):
                break
            time.sleep(0.005)
        self.assertIn({
            "id": "dynamic-tool-1",
            "error": {"code": -32601, "message": "This GUI does not support the requested client operation."},
        }, self.process.stdin.writes)
        event = next(event for event in self.bridge.events if event.kind == "server_request")
        self.assertEqual(event.data["params"]["accessToken"], "[REDACTED]")

    def test_protocol_error_secret_redaction_and_unexpected_exit(self):
        self._start()
        thread, result = self._request_in_thread(self.bridge.account_read)
        request = self._wait_for_write("account/read")
        self.process.stdout.emit({"id": request["id"], "error": {"code": 401, "message": "Bearer abc.def.ghi"}})
        thread.join(1)
        self.assertIsInstance(result["error"], BridgeProtocolError)
        self.assertIn("[REDACTED]", str(result["error"]))
        self.assertEqual(redact_secrets({"accessToken": "secret", "nested": "sk-secret-long"})["accessToken"], "[REDACTED]")
        redacted = redact_secrets({"verificationUrl": "https://secret", "userCode": "ABC", "jwt": "eyJaaa.bbb.ccc"})
        self.assertEqual(redacted["verificationUrl"], "[REDACTED]")
        self.assertEqual(redacted["userCode"], "[REDACTED]")
        self.assertEqual(redacted["jwt"], "[REDACTED]")

        self.process.returncode = 17
        self.process.stdout.close()
        for _ in range(100):
            if self.bridge.state is BridgeState.EXITED:
                break
            time.sleep(0.005)
        self.assertEqual(self.bridge.state, BridgeState.EXITED)
        self.assertTrue(any(event.kind == "unexpected_exit" for event in self.bridge.events))

    def test_request_before_start_is_unavailable(self):
        with self.assertRaises(BridgeUnavailableError):
            self.bridge.account_read()

    def test_restart_after_unexpected_exit_uses_a_fresh_transport(self):
        self.bridge.shutdown(wait_seconds=0)
        first, second = _FakeProcess(), _FakeProcess()
        processes = [first, second]
        bridge = CodexBridge(
            executable=sys.executable,
            process_factory=lambda *args, **kwargs: processes.pop(0),
        )
        try:
            thread, result = self._request_in_thread(bridge.start)
            for _ in range(100):
                if first.stdin.writes:
                    break
                time.sleep(0.005)
            initialize = next(item for item in first.stdin.writes if item.get("method") == "initialize")
            first.stdout.emit({"id": initialize["id"], "result": {}})
            thread.join(1)
            self.assertNotIn("error", result)
            first.returncode = 17
            first.stdout.close()
            for _ in range(100):
                if bridge.state is BridgeState.EXITED:
                    break
                time.sleep(0.005)
            thread, result = self._request_in_thread(bridge.restart)
            for _ in range(100):
                if second.stdin.writes:
                    break
                time.sleep(0.005)
            initialize = next(item for item in second.stdin.writes if item.get("method") == "initialize")
            second.stdout.emit({"id": initialize["id"], "result": {}})
            thread.join(1)
            self.assertNotIn("error", result)
            self.assertEqual(bridge.state, BridgeState.READY)
        finally:
            bridge.shutdown(wait_seconds=0)


if __name__ == "__main__":
    unittest.main()
