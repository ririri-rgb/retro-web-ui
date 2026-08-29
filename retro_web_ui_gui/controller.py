"""Application controller joining the GUI, deterministic CLI workflow, and Codex.

The controller is intentionally the composition boundary.  Widgets never see
raw App Server protocol messages and neither this class nor its dependencies
store API keys, browser login URLs, account identifiers, or tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Union

from .codex_bridge import BridgeEvent, CodexAvailability, CodexBridge, redact_secrets
from .core_facade import CommandResult as CoreCommandResult, CoreFacade
from .workflow import ConversionWorkflow, ResultClassification, VerificationApproval, WorkflowSnapshot, WorkflowState

try:  # Keep the controller importable in CLI-only installations.
    from PySide6.QtCore import QObject, Signal
except ImportError:  # pragma: no cover - exercised by package metadata tests
    QObject = object  # type: ignore[assignment,misc]
    Signal = None  # type: ignore[assignment]


class WindowPort(Protocol):
    def set_codex_state(self, state: str, message: str) -> None: ...
    def set_project(self, root: str, applications: list[Mapping[str, Any]] | None = None) -> None: ...
    def set_analysis(self, result: str) -> None: ...
    def add_agent_event(self, event: Mapping[str, Any]) -> None: ...
    def request_approval(self, request: Mapping[str, str]) -> bool: ...
    def request_user_input(self, request: Mapping[str, Any]) -> Mapping[str, list[str]]: ...
    def set_verification(self, text: str, *, result: str = "Review required") -> None: ...
    def set_diff(self, text: str) -> None: ...
    def set_models(self, models: list[Mapping[str, Any]], *, account_text: str = "Signed in with ChatGPT") -> None: ...
    def open_external_url(self, url: str) -> bool: ...
    def set_busy(self, busy: bool, message: str | None = None) -> None: ...


@dataclass(frozen=True)
class CommandRunResult:
    approval_id: int
    succeeded: bool
    output: str = ""


CommandRunner = Callable[[VerificationApproval], Union[CommandRunResult, bool]]


AGENT_RESULT_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "string",
            "enum": ["complete", "complete_with_review_items", "review_required", "unsupported"],
        },
        "summary": {"type": "string"},
        "changedFiles": {"type": "array", "items": {"type": "string"}},
        "reviewItems": {"type": "array", "items": {"type": "string"}},
        "verificationPerformed": {"type": "array", "items": {"type": "string"}},
        "verificationUnavailable": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "classification",
        "summary",
        "changedFiles",
        "reviewItems",
        "verificationPerformed",
        "verificationUnavailable",
    ],
    "additionalProperties": False,
}


class _ControllerLogic:
    """Toolkit-neutral controller logic; Qt subclasses only marshal callbacks."""

    def _initialize_controller(
        self,
        window: WindowPort,
        *,
        workflow: Optional[ConversionWorkflow] = None,
        facade: Optional[CoreFacade] = None,
        bridge: Optional[CodexBridge] = None,
        availability_detector: Optional[Callable[[], CodexAvailability]] = None,
        command_runner: Optional[CommandRunner] = None,
    ) -> None:
        self.window = window
        self.facade = facade or CoreFacade()
        self.workflow = workflow or ConversionWorkflow(self.facade)
        self.bridge = bridge or CodexBridge()
        self.availability_detector = availability_detector or (lambda: CodexBridge.detect(self.bridge.executable))
        self.command_runner = command_runner
        self.models: list[Mapping[str, Any]] = []
        self.thread_id: Optional[str] = None
        self.turn_id: Optional[str] = None
        self._bridge_started = False
        self._interrupt_requested = False
        self._login_id: Optional[str] = None
        self._agent_result: Optional[Mapping[str, Any]] = None
        self._agent_result_error: Optional[str] = None
        self._remove_listener = self.bridge.add_listener(self._bridge_listener)

    # Readiness/authentication ---------------------------------------------------
    def refresh_codex(self) -> CodexAvailability:
        availability = self.availability_detector()
        if not availability.available:
            detail = str(redact_secrets(availability.error or "the executable was not found on PATH"))
            self.window.set_codex_state(
                "unavailable",
                "Codex is not available. Install Codex, sign in with ChatGPT, and ensure the launcher is on PATH. "
                f"Local analysis remains available. Diagnostic: {detail}",
            )
            return availability
        try:
            if not self._bridge_started:
                self.bridge.start(cwd=self.workflow.project_root)
                self._bridge_started = True
            account = self.bridge.account_read()
            self.bridge.read_configuration(cwd=self.workflow.project_root)
            self.models = self._models_from(self.bridge.list_models())
        except Exception as error:
            detail = str(redact_secrets(str(error)))
            self.window.set_codex_state(
                "error",
                f"Codex App Server could not start ({type(error).__name__}): {detail}. "
                "Confirm that `codex app-server --help` works, then reconnect.",
            )
            return CodexAvailability(False, availability.executable, availability.version, str(error))
        account_type = self._account_type(account)
        if account_type is None:
            self.window.set_codex_state("auth_required", "Sign in with ChatGPT in Codex before starting semantic conversion.")
        elif account_type != "chatgpt":
            self.window.set_codex_state(
                "auth_required",
                f"Codex is authenticated with {account_type}, but this GUI requires the official ChatGPT sign-in session.",
            )
        else:
            setter = getattr(self.window, "set_models", None)
            if callable(setter):
                setter(self.models, account_text="Signed in with ChatGPT")
            self.window.set_codex_state(
                "ready",
                f"Codex is ready ({availability.version or 'version unavailable'}). "
                "Your existing ChatGPT sign-in will be used; no API key is requested.",
            )
        return availability

    def begin_chatgpt_login(self) -> Mapping[str, Any]:
        """Start the official browser login without retaining tokens or URLs."""
        if not self._bridge_started:
            self.refresh_codex()
        if not self._bridge_started:
            raise RuntimeError("Codex App Server is not ready.")
        result = self.bridge.begin_chatgpt_login()
        self._login_id = str(result.get("loginId")) if isinstance(result, Mapping) and result.get("loginId") else None
        auth_url = result.get("authUrl") if isinstance(result, Mapping) else None
        opener = getattr(self.window, "open_external_url", None)
        if auth_url and callable(opener):
            opener(str(auth_url))
        self.window.set_codex_state(
            "auth_required",
            "Complete the ChatGPT sign-in in your browser. This application does not store the sign-in URL or credentials.",
        )
        return {"type": result.get("type"), "loginId": self._login_id} if isinstance(result, Mapping) else {}

    def cancel_login(self) -> None:
        if self._login_id:
            self.bridge.cancel_login(self._login_id)
            self._login_id = None

    def reconnect(self) -> None:
        """Recreate the local transport and reload the durable thread state."""
        previous_thread = self.thread_id
        self.bridge.restart(cwd=self.workflow.project_root)
        self._bridge_started = True
        account = self.bridge.account_read()
        if self._account_type(account) != "chatgpt":
            self.window.set_codex_state("auth_required", "Reconnect succeeded, but ChatGPT sign-in is required.")
            return
        self.bridge.read_configuration(cwd=self.workflow.project_root)
        self.models = self._models_from(self.bridge.list_models())
        setter = getattr(self.window, "set_models", None)
        if callable(setter):
            setter(self.models, account_text="Signed in with ChatGPT")
        if previous_thread:
            self.bridge.resume_thread(previous_thread)
            restored = self.bridge.read_thread(previous_thread, include_turns=True)
            self.window.add_agent_event({
                "kind": "thread_recovered",
                "message": "Durable Codex thread state was reloaded after reconnect.",
                "detail": json.dumps(self._thread_recovery_summary(restored), ensure_ascii=False),
            })
        if self.workflow.project_root is not None:
            self.workflow.diff = self.facade.diff_summary(self.workflow.project_root)
            self.window.set_diff(self._format_diff(self.workflow.snapshot()))
        self.window.set_codex_state(
            "ready",
            "Codex App Server reconnected. Existing edits and the durable thread are available for review or retry.",
        )

    @staticmethod
    def _requires_login(account: Mapping[str, Any]) -> bool:
        return _ControllerLogic._account_type(account) is None

    @staticmethod
    def _account_type(account: Mapping[str, Any]) -> Optional[str]:
        value = account.get("account") if isinstance(account, Mapping) else None
        if not isinstance(value, Mapping) or not value.get("type"):
            return None
        return str(value["type"]).strip().lower()

    @staticmethod
    def _models_from(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        values = result.get("data", result.get("models", [])) if isinstance(result, Mapping) else []
        return [item if isinstance(item, Mapping) else {"id": str(item)} for item in values if item]

    # Deterministic workflow -----------------------------------------------------
    def select_project(self, root: str) -> WorkflowSnapshot:
        snapshot = self.workflow.prepare(root)
        candidates = self.workflow.analysis.result["selection"].get("candidates", []) if self.workflow.analysis else []
        self.window.set_project(str(snapshot.project_root), candidates)
        self.window.set_analysis(self._cli_summary(self.workflow.analysis))
        return snapshot

    def select_application(self, app: str) -> WorkflowSnapshot:
        snapshot = self.workflow.select_application(app)
        self.window.set_analysis(self._cli_summary(self.workflow.analysis))
        return snapshot

    def select_theme(self, theme_id: str) -> WorkflowSnapshot:
        return self.workflow.select_theme(theme_id)

    def create_baseline(self) -> WorkflowSnapshot:
        snapshot = self.workflow.create_baseline()
        self.window.add_agent_event({"kind": "baseline", "message": "Behavior baseline created outside the selected project."})
        return snapshot

    # Session and conversion -----------------------------------------------------
    def start_conversion(self, *, model: Optional[str] = None, effort: Optional[str] = None) -> Mapping[str, Any]:
        if not self._bridge_started:
            self.refresh_codex()
        if not self._bridge_started:
            raise RuntimeError("Codex App Server is not ready.")
        account = self.bridge.account_read()
        account_type = self._account_type(account)
        if account_type != "chatgpt":
            self.window.set_codex_state(
                "auth_required",
                "Sign in with ChatGPT in Codex before starting semantic conversion."
                if account_type is None
                else f"Codex is authenticated with {account_type}, but semantic conversion requires ChatGPT sign-in.",
            )
            raise RuntimeError("A current ChatGPT Codex session is required for semantic conversion.")
        snapshot = self.workflow.snapshot()
        if snapshot.baseline is None or snapshot.project_root is None or snapshot.selected_theme is None:
            raise RuntimeError("Select a project and theme, then create a behavior baseline before conversion.")
        if self.workflow.state == WorkflowState.AGENT_INTERRUPTED:
            # A retry starts a new bounded turn against the preserved diff and
            # the original external baseline; no user files are reverted.
            self.workflow.state = WorkflowState.BASELINE_READY
            self.workflow.classification = None
        self.workflow.begin_agent_conversion()
        self._agent_result = None
        self._agent_result_error = None
        busy = getattr(self.window, "set_busy", None)
        if callable(busy):
            busy(True, "Project, application, theme, and model are locked for this Codex turn.")
        application_root = self._application_root(snapshot)
        # Keep thread creation minimal. The explicit turn-level sandbox is the
        # auditable boundary that limits writes to the selected application.
        try:
            thread = self.bridge.start_thread(cwd=str(application_root))
            self.thread_id = self._thread_id(thread)
            skill_path = self.facade.skill_path
            turn = self.bridge.start_turn(
                self.thread_id,
                [
                    {"type": "skill", "name": "retro-web-ui", "path": str(skill_path)},
                    {"type": "text", "text": self._conversion_prompt(snapshot)},
                ],
                cwd=str(application_root),
                approvalPolicy="on-request",
                sandboxPolicy={
                    "type": "workspaceWrite",
                    "writableRoots": [str(application_root)],
                    "networkAccess": False,
                },
                outputSchema=AGENT_RESULT_SCHEMA,
                **{key: value for key, value in {"model": model, "effort": effort}.items() if value},
            )
        except Exception as error:
            self.thread_id = None
            self.turn_id = None
            self.workflow.state = WorkflowState.BASELINE_READY
            self.workflow.classification = None
            self._set_not_busy()
            self.window.set_codex_state(
                "error",
                f"Codex could not start the conversion turn ({type(error).__name__}). The baseline and user files were preserved.",
            )
            raise
        self.turn_id = self._turn_id(turn)
        self.window.set_codex_state("running", "Codex is converting the selected application. Review every requested operation.")
        return turn

    def interrupt(self) -> None:
        if self.thread_id:
            self.bridge.interrupt_turn(self.thread_id, self.turn_id)
            self._interrupt_requested = True
            self.window.set_codex_state("running", "Interrupt requested. Waiting for Codex to report the terminal interrupted state.")

    def close(self) -> None:
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        if self._bridge_started:
            self.bridge.shutdown()
            self._bridge_started = False
        self.workflow.cleanup()

    # Bridge events: scheduled onto the GUI thread by the Qt subclass. ----------
    def _bridge_listener(self, event: BridgeEvent) -> None:
        self._schedule_bridge_event(event)

    def _consume_bridge_event(self, event: BridgeEvent) -> None:
        if event.kind == "agent_message_delta":
            # Deltas are character/token fragments. The authoritative completed
            # agentMessage item below provides readable, bounded progress.
            return
        if event.kind == "approval_requested":
            approval = event.data.get("approval", {})
            if isinstance(approval, Mapping):
                request_id = approval.get("requestId")
                details = approval.get("details") if isinstance(approval.get("details"), Mapping) else {}
                kind = str(approval.get("kind") or "operation")
                command = " ".join(approval.get("command") or ()) or self._approval_operation(kind, details)
                allowed = self.window.request_approval({
                    "command": command,
                    "cwd": str(approval.get("cwd") or "(not supplied)"),
                    "reason": str(approval.get("reason") or "Codex requested this operation."),
                    "risk": self._approval_risk(kind, details),
                })
                if allowed:
                    self.bridge.approve(request_id)
                else:
                    self.bridge.deny(request_id)
            return
        if event.kind == "item_completed" and self._consume_completed_item(event):
            return
        if event.kind == "user_input_requested":
            request_id = event.data.get("requestId")
            details = event.data.get("details", {})
            requester = getattr(self.window, "request_user_input", None)
            answers = requester(details) if callable(requester) and isinstance(details, Mapping) else {}
            self.bridge.answer_user_input(request_id, answers)
            return
        if event.kind == "diff_updated":
            params = event.data.get("params", {})
            if isinstance(params, Mapping):
                self.window.set_diff(str(params.get("diff") or ""))
        elif event.kind == "turn_completed":
            self._complete_turn(event)
        elif event.kind == "login_completed":
            self._login_id = None
            self.refresh_codex()
        elif event.kind == "unexpected_exit":
            self.workflow.agent_interrupted()
            self._set_not_busy()
            self.window.set_codex_state("error", "Codex App Server exited unexpectedly. Review the diff and retry when ready.")
        self.window.add_agent_event({"kind": event.kind, "message": self._event_message(event), "detail": json.dumps(dict(event.data), ensure_ascii=False)[:2000]})

    def _consume_completed_item(self, event: BridgeEvent) -> bool:
        params = event.data.get("params") if isinstance(event.data, Mapping) else None
        item = params.get("item") if isinstance(params, Mapping) else None
        if not isinstance(item, Mapping):
            return False
        item_type = str(item.get("type") or "item")
        if item_type == "agentMessage":
            text = str(item.get("text") or "").strip()
            phase = str(item.get("phase") or "")
            event_thread = params.get("threadId") or item.get("threadId")
            event_turn = params.get("turnId") or item.get("turnId")
            active_item = bool(
                self.thread_id
                and self.turn_id
                and str(event_thread or "") == self.thread_id
                and str(event_turn or "") == self.turn_id
            )
            parsed = self._parse_agent_result(text) if phase in {"", "final_answer"} else None
            if parsed is not None and phase != "commentary" and active_item:
                self._agent_result = parsed
                message = str(parsed.get("summary") or "Codex completed its semantic assessment.")
                detail = json.dumps(parsed, ensure_ascii=False, indent=2)
            else:
                message = text or "Codex completed an agent message."
                detail = message
                if phase == "final_answer" and active_item:
                    self._agent_result = None
                    self._agent_result_error = "Codex final output did not match the required result schema."
                elif phase == "final_answer" and not active_item:
                    message = "A completed message from another or unidentified turn was not used as this result."
                    detail = json.dumps(dict(params), ensure_ascii=False, indent=2)
            self.window.add_agent_event({"kind": "agent_message", "message": message, "detail": detail[:4000]})
            return True
        status = str(item.get("status") or "completed")
        command = item.get("command")
        label = " ".join(map(str, command)) if isinstance(command, list) else str(command or item_type)
        self.window.add_agent_event({"kind": item_type, "message": f"{label}: {status}", "detail": json.dumps(dict(item), ensure_ascii=False)[:4000]})
        return True

    def _complete_turn(self, event: BridgeEvent) -> None:
        params = event.data.get("params", {})
        if not isinstance(params, Mapping):
            return
        turn = params.get("turn")
        event_thread = params.get("threadId")
        event_turn = params.get("turnId")
        if isinstance(turn, Mapping):
            event_thread = turn.get("threadId") or event_thread
            event_turn = turn.get("id") or event_turn
        if self.thread_id and event_thread not in {None, self.thread_id}:
            return
        if self.turn_id and event_turn not in {None, self.turn_id}:
            return
        turn_status = str(turn.get("status")) if isinstance(turn, Mapping) and turn.get("status") else "completed"
        if self._interrupt_requested or turn_status == "interrupted":
            self._interrupt_requested = False
            snapshot = self.workflow.agent_interrupted()
            self.window.set_diff(self._format_diff(snapshot))
            self.window.set_codex_state("interrupted", "The agent was interrupted. Existing edits were preserved for diff review.")
            self._set_not_busy()
            return
        if turn_status == "failed":
            self.workflow.state = WorkflowState.ERROR
            self.workflow.classification = ResultClassification.VERIFICATION_FAILED
            self.window.set_codex_state("error", "Codex reported a failed turn. Review the agent events and diff before retrying.")
            self._set_not_busy()
            return
        self.request_verification_approvals()
        command_results = self.run_authorized_verification_plans()
        snapshot = self.workflow.verify()
        snapshot = self.workflow.apply_agent_assessment(dict(self._agent_result) if self._agent_result else None)
        output = self._cli_summary(self.workflow.verification)
        if command_results:
            output += "\n\nTarget command results:\n" + "\n".join(
                f"{'OK' if item.succeeded else 'FAILED'}: {item.output}" for item in command_results
            )
        if self._agent_result:
            output += "\n\nCodex semantic assessment:\n" + json.dumps(dict(self._agent_result), ensure_ascii=False, indent=2)
        elif self._agent_result_error:
            output += "\n\nCodex semantic assessment: REVIEW REQUIRED\n" + self._agent_result_error
        else:
            output += "\n\nCodex semantic assessment: REVIEW REQUIRED\nNo structured final assessment was received."
        self.window.set_verification(output, result=(snapshot.classification.value if snapshot.classification else "Review required"))
        self.window.set_diff(self._format_diff(snapshot))
        self.window.set_codex_state("ready", "Codex turn completed. Review deterministic verification and the diff.")
        self._set_not_busy()

    def request_verification_approvals(self) -> None:
        for plan in self.workflow.verification_approvals():
            if plan.status != "pending":
                continue
            allowed = self.window.request_approval({
                "command": self._display_argv(plan.argv),
                "cwd": str(plan.working_directory),
                "reason": plan.reason,
                "risk": plan.risk,
            })
            self.workflow.set_verification_approval(plan.identifier, allowed)

    def run_authorized_verification_plans(self) -> list[CommandRunResult]:
        results: list[CommandRunResult] = []
        for plan in self.workflow.verification_approvals():
            if plan.status != "allowed":
                continue
            if self.command_runner is None:
                core_result = self.workflow.run_authorized_verification(plan.identifier)
                results.append(CommandRunResult(
                    plan.identifier,
                    not core_result.timed_out and core_result.returncode == 0,
                    self._command_output(core_result),
                ))
                continue
            raw = self.command_runner(plan)
            normalized = raw if isinstance(raw, CommandRunResult) else CommandRunResult(
                plan.identifier, bool(raw), "Target command runner returned no output."
            )
            self.workflow.command_results.append(CoreCommandResult(
                plan.argv,
                plan.working_directory,
                0 if normalized.succeeded else 1,
                normalized.output if normalized.succeeded else "",
                "" if normalized.succeeded else normalized.output,
                0.0,
                False,
            ))
            results.append(normalized)
        return results

    def _conversion_prompt(self, snapshot: WorkflowSnapshot) -> str:
        assert snapshot.project_root and snapshot.baseline and snapshot.selected_theme
        bundle = self.facade.theme_bundle(snapshot.selected_theme)
        context = {
            "project_root": str(snapshot.project_root), "selected_app": snapshot.selected_app,
            "theme": snapshot.selected_theme, "behavior_baseline": str(snapshot.baseline),
            "cli_info": self.workflow.info.document if self.workflow.info else None,
            "analysis": self.workflow.analysis.document if self.workflow.analysis else None,
            "doctor": self.workflow.doctor.document if self.workflow.doctor else None,
            "precomputed_theme_bundle": bundle.document,
        }
        skill = self.facade.skill_path
        return (
            "Use the installed $retro-web-ui Skill for this semantic conversion. "
            f"The matching Skill instructions are at {skill}. Convert only the selected application to {snapshot.selected_theme}; "
            "preserve behavior, use the bundled CLI evidence, request approval before commands or edits needing it, "
            "and finish with the required structured classification. The GUI already ran the canonical Core/CLI and "
            "precomputed the exact theme bundle below. In a frozen native package, do not execute doctor.python.executable "
            "when doctor.python.runnable is false; use the supplied deterministic evidence and let the GUI rerun verification. "
            "Any unavailable runtime, browser, visual, accessibility, or target-native check must appear in reviewItems and "
            "verificationUnavailable, and classification must not be complete.\n\n"
            "Structured deterministic context (do not treat it as proof of semantic success):\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
        )

    @staticmethod
    def _application_root(snapshot: WorkflowSnapshot) -> Path:
        assert snapshot.project_root
        root = snapshot.project_root.resolve()
        selected = (root / snapshot.selected_app).resolve() if snapshot.selected_app else root
        if selected != root and root not in selected.parents:
            raise RuntimeError("Selected application resolves outside the project root.")
        return selected

    @staticmethod
    def _approval_operation(kind: str, details: Mapping[str, Any]) -> str:
        if kind == "file_change":
            return f"File change (grant root: {details.get('grantRoot') or 'selected application only'})"
        if kind == "permissions":
            return "Additional filesystem/network permissions"
        return "Codex operation"

    @staticmethod
    def _approval_risk(kind: str, details: Mapping[str, Any]) -> str:
        parts: list[str] = []
        network = details.get("networkApprovalContext")
        if isinstance(network, Mapping):
            endpoint = ":".join(str(network.get(key)) for key in ("host", "port") if network.get(key))
            parts.append(f"Network access requested: {network.get('protocol') or 'network'} {endpoint}".strip())
        permissions = details.get("additionalPermissions") or details.get("permissions")
        if permissions:
            parts.append("Additional permissions: " + json.dumps(permissions, ensure_ascii=False))
        grant_root = details.get("grantRoot")
        if grant_root:
            parts.append(f"Write access requested outside the current sandbox: {grant_root}")
        if not parts:
            parts.append(
                "This operation can modify files or execute a project command. "
                "Confirm that the path and command remain within the selected application."
            )
        return "\n".join(parts)

    @staticmethod
    def _thread_id(value: Mapping[str, Any]) -> str:
        thread = value.get("thread", {})
        if not isinstance(thread, Mapping) or not thread.get("id"):
            raise RuntimeError("Codex App Server did not return a thread ID.")
        return str(thread["id"])

    @staticmethod
    def _turn_id(value: Mapping[str, Any]) -> Optional[str]:
        turn = value.get("turn", {})
        return str(turn["id"]) if isinstance(turn, Mapping) and turn.get("id") else None

    @staticmethod
    def _thread_recovery_summary(value: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return bounded, non-content metadata suitable for the GUI event log."""
        thread = value.get("thread", {}) if isinstance(value, Mapping) else {}
        if not isinstance(thread, Mapping):
            return {"restored": False}
        turns = thread.get("turns", [])
        statuses = [
            str(turn.get("status") or "unknown")
            for turn in turns[-10:]
            if isinstance(turn, Mapping)
        ] if isinstance(turns, list) else []
        return {"restored": True, "threadId": thread.get("id"), "turnCount": len(turns) if isinstance(turns, list) else 0, "recentStatuses": statuses}

    @staticmethod
    def _cli_summary(response: Any) -> str:
        if response is None:
            return "No deterministic result available."
        return json.dumps(response.document, ensure_ascii=False, indent=2)

    @staticmethod
    def _event_message(event: BridgeEvent) -> str:
        params = event.data.get("params") if isinstance(event.data, Mapping) else None
        if isinstance(params, Mapping):
            return str(params.get("message") or params.get("status") or event.kind)
        return event.kind

    @staticmethod
    def _parse_agent_result(text: str) -> Optional[Mapping[str, Any]]:
        if not text:
            return None
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(value, Mapping):
            return None
        required_lists = ("changedFiles", "reviewItems", "verificationPerformed", "verificationUnavailable")
        if str(value.get("classification")) not in {
            "complete", "complete_with_review_items", "review_required", "unsupported"
        }:
            return None
        if not isinstance(value.get("summary"), str):
            return None
        if any(not isinstance(value.get(key), list) or not all(isinstance(item, str) for item in value[key]) for key in required_lists):
            return None
        return dict(value)

    @staticmethod
    def _display_argv(argv: Sequence[str]) -> str:
        return subprocess.list2cmdline(list(argv)) if os.name == "nt" else shlex.join(argv)

    @staticmethod
    def _command_output(result: CoreCommandResult) -> str:
        status = "timed out" if result.timed_out else f"exit {result.returncode}"
        text = result.stdout or result.stderr
        return f"{status} in {result.duration_seconds:.2f}s\n{text[-4000:]}".rstrip()

    @staticmethod
    def _format_diff(snapshot: WorkflowSnapshot) -> str:
        if snapshot.diff is None:
            return "No Git diff is available."
        untracked = "\n".join(f"?? {path}" for path in snapshot.diff.untracked)
        return "\n\n".join(
            part for part in (snapshot.diff.stat.strip(), untracked, snapshot.diff.patch.strip()) if part
        )

    def _set_not_busy(self) -> None:
        setter = getattr(self.window, "set_busy", None)
        if callable(setter):
            setter(False)


if Signal is not None:
    class DesktopController(QObject, _ControllerLogic):
        """Qt controller: queued signals marshal App Server reader callbacks."""

        bridge_event_received = Signal(object)

        def __init__(self, window: WindowPort, **kwargs: Any) -> None:
            QObject.__init__(self)
            self._initialize_controller(window, **kwargs)
            self.bridge_event_received.connect(self._consume_bridge_event)

        def _schedule_bridge_event(self, event: BridgeEvent) -> None:
            self.bridge_event_received.emit(event)
else:
    class DesktopController(_ControllerLogic):
        """Headless composition variant used when the optional Qt extra is absent."""

        def __init__(self, window: WindowPort, **kwargs: Any) -> None:
            self._initialize_controller(window, **kwargs)

        def _schedule_bridge_event(self, event: BridgeEvent) -> None:
            self._consume_bridge_event(event)
