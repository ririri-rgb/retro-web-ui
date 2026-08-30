"""Application controller joining the GUI, deterministic CLI workflow, and Codex.

The controller is intentionally the composition boundary.  Widgets never see
raw App Server protocol messages and neither this class nor its dependencies
store API keys, browser login URLs, account identifiers, or tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Union

from .codex_bridge import BridgeEvent, CodexAvailability, CodexBridge, redact_secrets
from .core_facade import CommandResult as CoreCommandResult, CoreFacade
from .workflow import ConversionWorkflow, ResultClassification, VerificationApproval, WorkflowSnapshot, WorkflowState
from .workspace import IntegrityState, SessionRecord, SessionState, WorkspaceError, WorkspaceStore

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
        workspace: Optional[WorkspaceStore] = None,
    ) -> None:
        self.window = window
        self.facade = facade or CoreFacade()
        self.workflow = workflow or ConversionWorkflow(self.facade)
        self.bridge = bridge or CodexBridge()
        self.availability_detector = availability_detector or (
            lambda: CodexBridge.detect(
                self.bridge.executable,
                forbidden_roots=(self.workflow.project_root,) if self.workflow.project_root else (),
            )
        )
        self.command_runner = command_runner
        self.workspace = workspace
        self.workspace_project_id: Optional[str] = None
        self.workspace_session_id: Optional[str] = None
        self._workspace_session_projects: dict[str, str] = {}
        self.models: list[Mapping[str, Any]] = []
        self.thread_id: Optional[str] = None
        self.turn_id: Optional[str] = None
        self._bridge_started = False
        self._codex_ready = False
        self._interrupt_requested = False
        self._login_id: Optional[str] = None
        self._agent_result: Optional[Mapping[str, Any]] = None
        self._agent_result_error: Optional[str] = None
        self._remove_listener = self.bridge.add_listener(self._bridge_listener)
        if self.workspace is not None:
            self.workspace.reconcile_startup()

    # Readiness/authentication ---------------------------------------------------
    def refresh_codex(self) -> CodexAvailability:
        availability = self.availability_detector()
        if not availability.available:
            self._codex_ready = False
            detail = str(redact_secrets(availability.error or "the executable was not found on PATH"))
            self.window.set_codex_state(
                "unavailable",
                "Codex is not available. Install Codex, sign in with ChatGPT, and ensure its official app or launcher is discoverable. "
                f"Local analysis remains available. Diagnostic: {detail}",
            )
            self._sync_conversion_controls()
            return availability
        if availability.executable:
            # Pin the absolute path that passed detection so start() cannot
            # select a different launcher after a PATH change.
            self.bridge.executable = availability.executable
        try:
            if not self._bridge_started:
                self.bridge.start(cwd=self.workflow.project_root)
                self._bridge_started = True
            account = self.bridge.account_read()
            self.bridge.read_configuration(cwd=self.workflow.project_root)
            self.models = self._models_from(self.bridge.list_models())
        except Exception as error:
            self._codex_ready = False
            detail = str(redact_secrets(str(error)))
            self.window.set_codex_state(
                "error",
                f"Codex App Server could not start ({type(error).__name__}): {detail}. "
                "Confirm that `codex app-server --help` works, then reconnect.",
            )
            self._sync_conversion_controls()
            return CodexAvailability(False, availability.executable, availability.version, str(error))
        account_type = self._account_type(account)
        if account_type is None:
            self._codex_ready = False
            self.window.set_codex_state("auth_required", "Sign in with ChatGPT in Codex before starting semantic conversion.")
        elif account_type != "chatgpt":
            self._codex_ready = False
            self.window.set_codex_state(
                "auth_required",
                f"Codex is authenticated with {account_type}, but this GUI requires the official ChatGPT sign-in session.",
            )
        else:
            self._codex_ready = True
            setter = getattr(self.window, "set_models", None)
            if callable(setter):
                setter(self.models, account_text="Signed in with ChatGPT")
            self.window.set_codex_state(
                "ready",
                f"Codex is ready ({availability.version or 'version unavailable'}). "
                "Your existing ChatGPT sign-in will be used; no API key is requested.",
            )
        self._sync_conversion_controls()
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
        reconnect_state = "ready"
        reconnect_message = "Codex App Server reconnected. Existing edits and durable thread metadata are available for review."
        self.bridge.restart(cwd=self.workflow.project_root)
        self._bridge_started = True
        account = self.bridge.account_read()
        if self._account_type(account) != "chatgpt":
            self._codex_ready = False
            self.window.set_codex_state("auth_required", "Reconnect succeeded, but ChatGPT sign-in is required.")
            self._sync_conversion_controls()
            return
        self._codex_ready = True
        self.bridge.read_configuration(cwd=self.workflow.project_root)
        self.models = self._models_from(self.bridge.list_models())
        setter = getattr(self.window, "set_models", None)
        if callable(setter):
            setter(self.models, account_text="Signed in with ChatGPT")
        if previous_thread:
            self.bridge.resume_thread(previous_thread)
            restored = self.bridge.read_thread(previous_thread, include_turns=True)
            if self.workflow.state == WorkflowState.AGENT_INTERRUPTED:
                try:
                    thread = self._validated_recovered_thread(restored, previous_thread)
                    remote_status, last_turn = self._remote_turn_status(thread)
                    if remote_status in self._active_remote_statuses():
                        self.workflow.state = WorkflowState.AGENT_RUNNING
                        self.workflow.classification = None
                        self.turn_id = str(last_turn.get("id") or self.turn_id or "") or None
                        self._transition_workspace(
                            SessionState.RUNNING,
                            thread_id=previous_thread,
                            turn_id=self.turn_id,
                            recovery_reason="Reconnect confirmed that the durable turn is still active.",
                        )
                        busy = getattr(self.window, "set_busy", None)
                        if callable(busy):
                            busy(True, "Reconnected Codex turn remains active; project and history controls stay locked.")
                        reconnect_state = "running"
                        reconnect_message = "Codex reconnected and reports that the existing turn is still active. Review or interrupt it before starting new work."
                    elif remote_status in self._terminal_remote_statuses():
                        self.turn_id = None
                        self._transition_workspace(
                            SessionState.INTERRUPTED_RECOVERABLE,
                            thread_id=previous_thread,
                            clear_turn_id=True,
                            recovery_reason="Reconnect confirmed a terminal remote turn; no turn was automatically resumed.",
                        )
                    else:
                        self.workflow.state = WorkflowState.ERROR
                        self.workflow.classification = None
                        reconnect_state = "error"
                        reconnect_message = "Codex reconnected, but the durable turn status is unknown. Recover the session explicitly before starting new work."
                except (RuntimeError, WorkspaceError):
                    self.workflow.state = WorkflowState.ERROR
                    self.workflow.classification = None
                    reconnect_state = "error"
                    reconnect_message = "Codex reconnected, but the durable thread identity could not be verified. New conversion remains disabled."
            self.window.add_agent_event({
                "kind": "thread_recovered",
                "message": "Durable Codex thread state was reloaded after reconnect.",
                "detail": json.dumps(self._thread_recovery_summary(restored), ensure_ascii=False),
            })
        if self.workflow.project_root is not None:
            self.workflow.diff = self.facade.diff_summary(self.workflow.project_root)
            self.window.set_diff(self._format_diff(self.workflow.snapshot()))
        self.window.set_codex_state(
            reconnect_state,
            reconnect_message,
        )
        self._sync_conversion_controls()

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

    # Durable workspace --------------------------------------------------------
    def restore_workspace(self) -> None:
        """Restore inspectable metadata without reinterpreting current source state."""
        if self.workspace is None:
            return
        projects: list[Mapping[str, Any]] = []
        sessions: list[Mapping[str, Any]] = []
        self._workspace_session_projects.clear()
        for project in self.workspace.list_projects():
            projects.append({
                "project_id": project.project_id,
                "display_name": project.display_name,
                "canonical_path": project.canonical_root,
                "availability": self.workspace.project_availability(project.project_id),
            })
            for session in self.workspace.list_sessions(project.project_id):
                self._workspace_session_projects[session.session_id] = project.project_id
                sessions.append(self._session_summary(session))
        setter = getattr(self.window, "set_workspace_projects", None)
        if callable(setter):
            setter(projects)
        setter = getattr(self.window, "set_workspace_sessions", None)
        if callable(setter):
            setter(sorted(sessions, key=lambda item: str(item.get("updated_at") or ""), reverse=True))
        issues = self.workspace.list_issues()
        if issues:
            detail = "Workspace metadata issues were preserved and excluded from normal history:\n" + "\n".join(
                f"- {item.get('kind')}: {item.get('error')}" for item in issues
            )
            setter = getattr(self.window, "set_session_detail", None)
            if callable(setter):
                setter(detail)

    def open_registered_project(self, project_id: str) -> WorkflowSnapshot:
        if self.workspace is None:
            raise RuntimeError("Workspace history is unavailable.")
        project = self.workspace.get_project(project_id)
        availability = self.workspace.project_availability(project_id)
        if availability != "available":
            raise RuntimeError(f"Registered project is not currently available ({availability}).")
        return self.select_project(project.canonical_root)

    def inspect_session(self, session_id: str) -> Mapping[str, Any]:
        if self.workspace is None:
            raise RuntimeError("Workspace history is unavailable.")
        project_id = self._workspace_session_projects.get(session_id)
        if project_id is None:
            self.restore_workspace()
            project_id = self._workspace_session_projects.get(session_id)
        if project_id is None:
            raise KeyError(f"Unknown conversion session: {session_id}")
        session = self.workspace.get_session(project_id, session_id)
        artifact_rows = []
        for name in sorted(session.artifacts):
            status = self.workspace.artifact_status(project_id, session_id, name)
            artifact_rows.append({"name": name, "integrity": status.integrity.value, "reason": status.reason})
        detail = {
            **self._session_summary(session),
            "project_availability": self.workspace.project_availability(project_id, session_id),
            "historical_observation": True,
            "artifacts": artifact_rows,
            "note": "This is recorded session evidence. It is not the current working tree and does not prove semantic or visual equivalence.",
        }
        setter = getattr(self.window, "set_session_detail", None)
        if callable(setter):
            setter(json.dumps(detail, ensure_ascii=False, indent=2))
        verification = self._historical_artifact_text(project_id, session_id, "verification.json")
        setter = getattr(self.window, "set_verification", None)
        if callable(setter):
            if verification is not None:
                setter(
                    "HISTORICAL SESSION EVIDENCE — not current verification\n\n" + verification,
                    result=session.classification or session.state.value,
                )
            else:
                setter(
                    "HISTORICAL SESSION EVIDENCE\n\nVerification was not captured or is no longer available with valid integrity.",
                    result=session.classification or "review_required",
                )
        historical_diff_found = False
        for name in ("git-end.json", "git-interrupted.json", "git-transport-lost.json", "git-close.json", "git-start.json"):
            historical_diff = self._historical_artifact_text(project_id, session_id, name)
            if historical_diff is not None:
                setter = getattr(self.window, "set_diff", None)
                if callable(setter):
                    setter(f"HISTORICAL SESSION METADATA ({name}) — not the current Git diff\n\n{historical_diff}")
                historical_diff_found = True
                break
        if not historical_diff_found:
            setter = getattr(self.window, "set_diff", None)
            if callable(setter):
                setter("HISTORICAL SESSION SNAPSHOT\n\nNo captured Git metadata is available with valid integrity. Raw patches are not persisted by default.")
        image_setter = getattr(self.window, "set_before_after", None)
        if callable(image_setter):
            before = self.workspace.artifact_status(project_id, session_id, "before.png")
            after = self.workspace.artifact_status(project_id, session_id, "after.png")
            image_setter(
                before.path if before.integrity == IntegrityState.AVAILABLE else None,
                after.path if after.integrity == IntegrityState.AVAILABLE else None,
            )
        return detail

    def compare_sessions(self, left_session_id: str, right_session_id: str) -> Mapping[str, Any]:
        if self.workspace is None:
            raise RuntimeError("Workspace history is unavailable.")
        left_project = self._workspace_session_projects.get(left_session_id)
        right_project = self._workspace_session_projects.get(right_session_id)
        if left_project is None or right_project is None:
            self.restore_workspace()
            left_project = self._workspace_session_projects.get(left_session_id)
            right_project = self._workspace_session_projects.get(right_session_id)
        if not left_project or left_project != right_project:
            report: Mapping[str, Any] = {
                "status": "not_comparable",
                "reason": "Sessions from different or unavailable projects are not compared as equivalent source histories.",
                "leftSessionId": left_session_id,
                "rightSessionId": right_session_id,
            }
        else:
            report = {
                "status": "ok",
                **self.workspace.compare_sessions(left_project, left_session_id, right_session_id),
                "left": self._session_summary(self.workspace.get_session(left_project, left_session_id)),
                "right": self._session_summary(self.workspace.get_session(left_project, right_session_id)),
                "note": "Artifact equality compares recorded bytes and integrity only; it does not rank visual quality.",
            }
        setter = getattr(self.window, "set_session_detail", None)
        if callable(setter):
            setter(json.dumps(report, ensure_ascii=False, indent=2))
        image_setter = getattr(self.window, "set_before_after", None)
        if callable(image_setter):
            image_setter(None, None)
        return report

    def recover_session(self, session_id: str) -> Mapping[str, Any]:
        """Explicitly reload a bound durable thread for review, never auto-resume a turn."""
        if self.workspace is None:
            raise RuntimeError("Workspace history is unavailable.")
        project_id = self._workspace_session_projects.get(session_id)
        if project_id is None:
            self.restore_workspace()
            project_id = self._workspace_session_projects.get(session_id)
        if project_id is None:
            raise KeyError(f"Unknown conversion session: {session_id}")
        session = self.workspace.get_session(project_id, session_id)
        if session.state not in {SessionState.TRANSPORT_LOST, SessionState.INTERRUPTED_RECOVERABLE}:
            raise RuntimeError(f"Session state {session.state.value} does not require Codex thread recovery.")
        if not session.thread_id:
            raise RuntimeError("The interrupted session has no durable Codex thread reference.")
        if self.workspace.project_availability(project_id, session_id) != "available":
            raise RuntimeError("The session's exact project/application binding is no longer available.")
        baseline = self.workspace.artifact_status(project_id, session_id, "behavior-baseline.json")
        if baseline.integrity != IntegrityState.AVAILABLE or not baseline.path:
            raise RuntimeError(f"The historical behavior baseline is {baseline.integrity.value}; recovery cannot reuse it.")
        project = self.workspace.get_project(project_id)
        self.select_project(project.canonical_root)
        if session.selected_app != ".":
            self.select_application(session.selected_app)
        if session.theme:
            self.select_theme(session.theme)
        restored = self._read_recovery_thread(session.thread_id)
        thread = self._validated_recovered_thread(restored, session.thread_id)
        application_root = self._application_root(self.workflow.snapshot())
        remote_cwd = thread.get("cwd") or thread.get("workingDirectory")
        binding_verified = False
        if remote_cwd:
            if Path(str(remote_cwd)).expanduser().resolve() != application_root:
                raise RuntimeError("Recovered Codex thread is bound to a different application directory.")
            binding_verified = True
        remote_status, last_turn = self._remote_turn_status(thread)
        self.workflow.baseline = Path(baseline.path)
        self.workspace_project_id = project_id
        self.workspace_session_id = session_id
        self.thread_id = session.thread_id
        if remote_status in self._active_remote_statuses():
            self.turn_id = str(last_turn.get("id") or session.turn_id or "") or None
            self.workflow.state = WorkflowState.AGENT_RUNNING
            self.workflow.classification = None
            self._transition_workspace(
                SessionState.RUNNING,
                thread_id=session.thread_id,
                turn_id=self.turn_id,
                recovery_reason="Codex reports that the durable turn is still active; no new session may start.",
            )
            state = "running"
            message = "Historical thread reloaded; Codex reports its last turn is still active. Review or interrupt it before starting new work."
            busy = getattr(self.window, "set_busy", None)
            if callable(busy):
                busy(True, "Recovered Codex turn is still active; project and history controls remain locked.")
        elif remote_status in self._terminal_remote_statuses():
            self.turn_id = None
            self.workflow.state = WorkflowState.AGENT_INTERRUPTED
            self.workflow.classification = ResultClassification.AGENT_INTERRUPTED
            self._transition_workspace(
                SessionState.INTERRUPTED_RECOVERABLE,
                thread_id=session.thread_id,
                clear_turn_id=True,
                recovery_reason="The durable thread was reloaded for review and its remote turn is terminal. No turn was automatically resumed.",
            )
            state = "ready"
            message = "Historical thread recovered for review. The remote turn is terminal; no turn was automatically resumed."
        else:
            self.thread_id = None
            self.turn_id = None
            self.workflow.state = WorkflowState.ERROR
            self.workflow.classification = None
            state = "error"
            message = "Thread metadata was reloaded, but Codex did not provide a recognized terminal or active status. New conversion remains disabled."
        summary = {**self._thread_recovery_summary(restored), "remoteStatus": remote_status, "bindingVerified": binding_verified}
        self.window.add_agent_event({
            "kind": "thread_recovered",
            "message": "Durable Codex thread metadata was reloaded. " + ("Server-side application binding matched." if binding_verified else "Server-side application binding was not supplied; only local binding is verified."),
            "detail": json.dumps(summary, ensure_ascii=False),
        })
        self.window.set_codex_state(state, message)
        self.restore_workspace()
        self._sync_conversion_controls()
        return summary

    def _read_recovery_thread(self, thread_id: str) -> Mapping[str, Any]:
        """Read durable remote metadata under an explicit, exception-safe UI lock."""
        busy = getattr(self.window, "set_busy", None)
        if callable(busy):
            busy(True, "Recovering durable Codex thread metadata for review.")
        try:
            if not self._bridge_started:
                self.refresh_codex()
            if not self._bridge_started or not self._codex_ready:
                raise RuntimeError("Codex App Server and ChatGPT sign-in are required to inspect the durable thread.")
            self.bridge.resume_thread(thread_id)
            return self.bridge.read_thread(thread_id, include_turns=True)
        finally:
            if callable(busy):
                busy(False)

    @staticmethod
    def _validated_recovered_thread(value: Mapping[str, Any], expected_thread_id: str) -> Mapping[str, Any]:
        thread = value.get("thread") if isinstance(value, Mapping) else None
        if not isinstance(thread, Mapping) or str(thread.get("id") or "") != expected_thread_id:
            raise RuntimeError("Codex returned a different or missing durable thread identifier.")
        return thread

    @staticmethod
    def _remote_turn_status(thread: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
        turns = thread.get("turns") if isinstance(thread.get("turns"), list) else []
        last_turn = turns[-1] if turns and isinstance(turns[-1], Mapping) else {}
        raw = last_turn.get("status") or thread.get("status") or "unknown"
        if isinstance(raw, Mapping):
            raw = raw.get("type") or raw.get("status") or "unknown"
        status = str(raw).strip().lower().replace("-", "_")
        return status, last_turn

    @staticmethod
    def _active_remote_statuses() -> set[str]:
        return {"running", "active", "in_progress", "pending", "queued", "starting"}

    @staticmethod
    def _terminal_remote_statuses() -> set[str]:
        return {"completed", "complete", "idle", "interrupted", "failed", "cancelled", "canceled"}

    @staticmethod
    def _session_summary(session: SessionRecord) -> Mapping[str, Any]:
        return {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "selected_app": session.selected_app,
            "theme": session.theme,
            "model": session.model,
            "reasoning_effort": session.reasoning_effort,
            "state": session.state.value,
            "classification": session.classification,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "thread_id": session.thread_id,
            "turn_id": session.turn_id,
            "failure_reason": session.failure_reason,
            "recovery_reason": session.recovery_reason,
        }

    def _historical_artifact_text(self, project_id: str, session_id: str, name: str) -> Optional[str]:
        assert self.workspace is not None
        status = self.workspace.artifact_status(project_id, session_id, name)
        if status.integrity != IntegrityState.AVAILABLE or not status.path:
            return None
        try:
            return Path(status.path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    # Deterministic workflow -----------------------------------------------------
    def select_project(self, root: str) -> WorkflowSnapshot:
        snapshot = self.workflow.prepare(root)
        if self.workspace is not None and snapshot.project_root is not None:
            project = self.workspace.open_project(snapshot.project_root)
            self.workspace_project_id = project.project_id
            self.workspace_session_id = None
        candidates = self.workflow.analysis.result["selection"].get("candidates", []) if self.workflow.analysis else []
        self.window.set_project(str(snapshot.project_root), candidates)
        self.window.set_analysis(self._cli_summary(self.workflow.analysis))
        self.restore_workspace()
        self._sync_conversion_controls()
        return snapshot

    def select_application(self, app: str) -> WorkflowSnapshot:
        snapshot = self.workflow.select_application(app)
        self.window.set_analysis(self._cli_summary(self.workflow.analysis))
        self._sync_conversion_controls()
        return snapshot

    def select_theme(self, theme_id: str) -> WorkflowSnapshot:
        snapshot = self.workflow.select_theme(theme_id)
        self._sync_conversion_controls()
        return snapshot

    def create_baseline(self) -> WorkflowSnapshot:
        snapshot = self.workflow.create_baseline()
        self.window.add_agent_event({"kind": "baseline", "message": "Behavior baseline created outside the selected project."})
        self._sync_conversion_controls()
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
        if self.workflow.state not in {WorkflowState.BASELINE_READY, WorkflowState.AGENT_INTERRUPTED}:
            raise RuntimeError(f"Conversion cannot start from workflow state {self.workflow.state.value}.")
        if self.workflow.state == WorkflowState.AGENT_INTERRUPTED:
            # A retry starts a new bounded turn against the preserved diff and
            # the original external baseline; no user files are reverted.
            self.workflow.state = WorkflowState.BASELINE_READY
            self.workflow.classification = None
        self._begin_workspace_session(snapshot, model=model, effort=effort)
        snapshot = self.workflow.snapshot()
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
            self._transition_workspace(SessionState.RUNNING, thread_id=self.thread_id, model=model, reasoning_effort=effort)
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
            self._transition_workspace(
                SessionState.FAILED,
                classification="failed",
                failure_reason=f"Codex turn start failed: {type(error).__name__}",
            )
            self.thread_id = None
            self.turn_id = None
            self.workflow.state = WorkflowState.BASELINE_READY
            self.workflow.classification = None
            self._set_not_busy()
            self.window.set_codex_state(
                "error",
                f"Codex could not start the conversion turn ({type(error).__name__}). The baseline and user files were preserved.",
            )
            self.restore_workspace()
            self._sync_conversion_controls()
            raise
        self.turn_id = self._turn_id(turn)
        if self.turn_id:
            self._transition_workspace(SessionState.RUNNING, turn_id=self.turn_id)
        self.restore_workspace()
        self.window.set_codex_state("running", "Codex is converting the selected application. Review every requested operation.")
        self._sync_conversion_controls()
        return turn

    def interrupt(self) -> None:
        if self.thread_id:
            try:
                self.bridge.interrupt_turn(self.thread_id, self.turn_id)
            except Exception as error:
                self._codex_ready = False
                self._bridge_started = False
                self._interrupt_requested = False
                self.workflow.state = WorkflowState.ERROR
                self.workflow.classification = None
                self._capture_git_evidence("transport-lost")
                try:
                    self._transition_workspace(
                        SessionState.TRANSPORT_LOST,
                        recovery_reason=f"Codex interrupt transport failed: {type(error).__name__}. Remote turn state must be checked before retry.",
                    )
                except WorkspaceError:
                    pass
                self._set_not_busy()
                self.window.set_codex_state(
                    "error",
                    "Codex could not confirm the interrupt because the transport failed. Reconnect and recover the thread status before starting new work.",
                )
                self.restore_workspace()
                self._sync_conversion_controls()
                return
            self._interrupt_requested = True
            self.window.set_codex_state("running", "Interrupt requested. Waiting for Codex to report the terminal interrupted state.")
            self._sync_conversion_controls()

    def close(self) -> None:
        if self.workspace is not None and self.workspace_project_id and self.workspace_session_id:
            try:
                session = self.workspace.get_session(self.workspace_project_id, self.workspace_session_id)
                if session.state in {
                    SessionState.RUNNING,
                    SessionState.AWAITING_APPROVAL,
                    SessionState.VERIFYING,
                    SessionState.VERIFICATION_PENDING,
                }:
                    self._capture_git_evidence("close")
                    self._transition_workspace(
                        SessionState.TRANSPORT_LOST,
                        recovery_reason="The desktop application closed before the session reached a terminal state.",
                    )
            except WorkspaceError:
                pass
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        if self._bridge_started:
            self.bridge.shutdown()
            self._bridge_started = False
        self.workflow.cleanup()

    def _begin_workspace_session(self, snapshot: WorkflowSnapshot, *, model: Optional[str], effort: Optional[str]) -> None:
        if self.workspace is None:
            return
        assert snapshot.project_root and snapshot.baseline and snapshot.selected_theme
        if self.workspace_project_id is None:
            self.workspace_project_id = self.workspace.open_project(snapshot.project_root).project_id
        session = self.workspace.create_session(
            self.workspace_project_id,
            selected_app=snapshot.selected_app or ".",
            theme=snapshot.selected_theme,
            model=model,
            reasoning_effort=effort,
        )
        self.workspace_session_id = session.session_id
        try:
            stored = self.workspace.capture_artifact(
                session.project_id,
                session.session_id,
                "behavior-baseline.json",
                snapshot.baseline,
                allowed_root=snapshot.baseline.parent,
            )
            if stored.integrity != IntegrityState.AVAILABLE or not stored.path:
                raise WorkspaceError("The durable behavior baseline could not be verified after capture.")
            # Remove only the original narrowly-scoped temporary baseline, then
            # make the immutable session copy authoritative for this workflow.
            self.workflow.cleanup()
            self.workflow.baseline = Path(stored.path)
            for name, response in (("analysis.json", self.workflow.analysis), ("doctor.json", self.workflow.doctor)):
                if response is not None:
                    try:
                        self.workspace.capture_json(session.project_id, session.session_id, name, response.document)
                    except WorkspaceError as error:
                        self.window.add_agent_event({
                            "kind": "workspace_evidence",
                            "message": f"{name} was not persisted: {type(error).__name__}",
                        })
            self._capture_git_evidence("start")
            self._transition_workspace(SessionState.PREPARED, model=model, reasoning_effort=effort)
            self.restore_workspace()
        except Exception as error:
            try:
                self._transition_workspace(
                    SessionState.FAILED,
                    classification="failed",
                    failure_reason=f"Workspace preparation failed: {type(error).__name__}",
                )
            except WorkspaceError:
                pass
            raise

    def _capture_git_evidence(self, phase: str) -> None:
        if not (self.workspace and self.workspace_project_id and self.workspace_session_id and self.workflow.project_root):
            return
        git = self.facade.git_state(self.workflow.project_root)
        diff = self.facade.diff_summary(self.workflow.project_root)
        document = {
            "capturedPhase": phase,
            "repository": git.repository,
            "dirty": git.dirty,
            "head": git.head,
            "entries": list(git.entries),
            "diffAvailable": diff.available,
            "files": list(diff.files),
            "untracked": list(diff.untracked),
            "stat": diff.stat,
            "patchBytes": len(diff.patch.encode("utf-8", errors="replace")),
            "patchSha256": hashlib.sha256(diff.patch.encode("utf-8", errors="replace")).hexdigest() if diff.patch else None,
            "attribution": "working-tree observation; not proof that every change belongs to this session",
            "privacy": "raw patch content is intentionally not persisted",
        }
        try:
            self.workspace.capture_json(
                self.workspace_project_id,
                self.workspace_session_id,
                f"git-{phase}.json",
                document,
            )
        except WorkspaceError as error:
            self.window.add_agent_event({
                "kind": "workspace_evidence",
                "message": f"Git {phase} evidence was not fully persisted: {type(error).__name__}",
            })

    def _transition_workspace(self, state: SessionState, **kwargs: Any) -> Optional[SessionRecord]:
        if not (self.workspace and self.workspace_project_id and self.workspace_session_id):
            return None
        return self.workspace.transition(self.workspace_project_id, self.workspace_session_id, state, **kwargs)

    @staticmethod
    def _workspace_outcome(classification: Optional[ResultClassification]) -> SessionState:
        if classification == ResultClassification.COMPLETE:
            return SessionState.COMPLETE
        if classification == ResultClassification.COMPLETE_WITH_REVIEW_ITEMS:
            return SessionState.COMPLETE_WITH_REVIEW_ITEMS
        if classification == ResultClassification.BEHAVIOR_INCOMPATIBILITY:
            return SessionState.BEHAVIOR_INCOMPATIBILITY
        if classification == ResultClassification.VERIFICATION_FAILED:
            return SessionState.FAILED
        if classification == ResultClassification.AGENT_INTERRUPTED:
            return SessionState.INTERRUPTED_RECOVERABLE
        return SessionState.REVIEW_REQUIRED

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
                if not self._active_event_matches(approval.get("threadId"), approval.get("turnId")):
                    self.bridge.deny(request_id)
                    self.window.add_agent_event({"kind": "stale_event", "message": "An approval request outside the active thread/turn was denied."})
                    return
                try:
                    self._transition_workspace(SessionState.AWAITING_APPROVAL)
                except WorkspaceError:
                    pass
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
                try:
                    self._transition_workspace(SessionState.RUNNING)
                except WorkspaceError:
                    pass
            return
        if event.kind == "item_completed" and self._consume_completed_item(event):
            return
        if event.kind == "user_input_requested":
            request_id = event.data.get("requestId")
            details = event.data.get("details", {})
            if not isinstance(details, Mapping) or not self._active_event_matches(details.get("threadId"), details.get("turnId")):
                self.bridge.answer_user_input(request_id, {})
                self.window.add_agent_event({"kind": "stale_event", "message": "A user-input request outside the active thread/turn was dismissed."})
                return
            requester = getattr(self.window, "request_user_input", None)
            try:
                self._transition_workspace(SessionState.AWAITING_APPROVAL)
            except WorkspaceError:
                pass
            answers = requester(details) if callable(requester) and isinstance(details, Mapping) else {}
            self.bridge.answer_user_input(request_id, answers)
            try:
                self._transition_workspace(SessionState.RUNNING)
            except WorkspaceError:
                pass
            return
        if event.kind == "diff_updated":
            params = event.data.get("params", {})
            if isinstance(params, Mapping) and self._active_event_matches(params.get("threadId"), params.get("turnId")):
                self.window.set_diff(str(params.get("diff") or ""))
        elif event.kind == "turn_completed":
            self._complete_turn(event)
        elif event.kind == "login_completed":
            self._login_id = None
            self.refresh_codex()
        elif event.kind == "unexpected_exit":
            self._codex_ready = False
            self._bridge_started = False
            if self.workflow.state == WorkflowState.AGENT_RUNNING and self.workflow.project_root and self.thread_id:
                self.workflow.agent_interrupted()
                self._capture_git_evidence("transport-lost")
                try:
                    self._transition_workspace(
                        SessionState.TRANSPORT_LOST,
                        recovery_reason="Codex App Server exited unexpectedly; the recorded thread may be inspected after reconnect.",
                    )
                except WorkspaceError:
                    pass
                self.restore_workspace()
            self._set_not_busy()
            self.window.set_codex_state("error", "Codex App Server exited unexpectedly. Reconnect, then review durable thread status and the current diff.")
            self._sync_conversion_controls()
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
        if not self._active_event_matches(event_thread, event_turn):
            return
        turn_status = str(turn.get("status")) if isinstance(turn, Mapping) and turn.get("status") else "completed"
        if self._interrupt_requested or turn_status == "interrupted":
            self._interrupt_requested = False
            snapshot = self.workflow.agent_interrupted()
            self._capture_git_evidence("interrupted")
            self._transition_workspace(
                SessionState.INTERRUPTED_RECOVERABLE,
                classification=ResultClassification.AGENT_INTERRUPTED.value,
                recovery_reason="The Codex turn was interrupted; existing source edits were preserved for review.",
            )
            self.window.set_diff(self._format_diff(snapshot))
            self.window.set_codex_state("interrupted", "The agent was interrupted. Existing edits were preserved for diff review.")
            self._set_not_busy()
            self.restore_workspace()
            self._sync_conversion_controls()
            return
        if turn_status == "failed":
            self.workflow.state = WorkflowState.ERROR
            self.workflow.classification = ResultClassification.VERIFICATION_FAILED
            self._capture_git_evidence("failed")
            self._transition_workspace(
                SessionState.FAILED,
                classification=ResultClassification.VERIFICATION_FAILED.value,
                failure_reason="Codex reported a failed turn.",
            )
            self.window.set_codex_state("error", "Codex reported a failed turn. Review the agent events and diff before retrying.")
            self._set_not_busy()
            self.restore_workspace()
            self._sync_conversion_controls()
            return
        self._transition_workspace(SessionState.VERIFYING)
        self.request_verification_approvals()
        command_results = self.run_authorized_verification_plans()
        snapshot = self.workflow.verify()
        snapshot = self.workflow.apply_agent_assessment(dict(self._agent_result) if self._agent_result else None)
        if self.workspace and self.workspace_project_id and self.workspace_session_id:
            if self.workflow.verification is not None:
                try:
                    self.workspace.capture_json(
                        self.workspace_project_id,
                        self.workspace_session_id,
                        "verification.json",
                        self.workflow.verification.document,
                    )
                except WorkspaceError as error:
                    self.window.add_agent_event({
                        "kind": "workspace_evidence",
                        "message": f"Verification evidence was not persisted: {type(error).__name__}",
                    })
            if self._agent_result:
                try:
                    self.workspace.capture_json(
                        self.workspace_project_id,
                        self.workspace_session_id,
                        "agent-assessment.json",
                        dict(self._agent_result),
                    )
                except WorkspaceError as error:
                    self.window.add_agent_event({
                        "kind": "workspace_evidence",
                        "message": f"Agent assessment was not persisted: {type(error).__name__}",
                    })
        self._capture_git_evidence("end")
        outcome = self._workspace_outcome(snapshot.classification)
        self._transition_workspace(
            outcome,
            classification=snapshot.classification.value if snapshot.classification else "review_required",
        )
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
        self.restore_workspace()
        self._sync_conversion_controls()

    def request_verification_approvals(self) -> None:
        plans = [plan for plan in self.workflow.verification_approvals() if plan.status == "pending"]
        if plans:
            self._transition_workspace(SessionState.VERIFICATION_PENDING)
        for plan in plans:
            allowed = self.window.request_approval({
                "command": self._display_argv(plan.argv),
                "cwd": str(plan.working_directory),
                "reason": plan.reason,
                "risk": plan.risk,
            })
            self.workflow.set_verification_approval(plan.identifier, allowed)
        if plans:
            self._transition_workspace(SessionState.VERIFYING)

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

    def _application_root(self, snapshot: WorkflowSnapshot) -> Path:
        assert snapshot.project_root
        return self.facade.contained_path(
            snapshot.project_root,
            snapshot.selected_app or ".",
            require_directory=True,
        )

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

    def _active_event_matches(self, thread_id: Any, turn_id: Any) -> bool:
        """Bind all mutating App Server events to the one active conversion turn."""
        return bool(
            self.thread_id
            and self.turn_id
            and thread_id is not None
            and turn_id is not None
            and str(thread_id) == self.thread_id
            and str(turn_id) == self.turn_id
        )

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

    def _sync_conversion_controls(self) -> None:
        setter = getattr(self.window, "set_conversion_controls", None)
        if not callable(setter):
            return
        state = self.workflow.state
        running = state == WorkflowState.AGENT_RUNNING
        setter(
            can_start=self._codex_ready and state in {WorkflowState.BASELINE_READY, WorkflowState.AGENT_INTERRUPTED},
            can_interrupt=running and bool(self.thread_id),
            busy=running,
        )


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
