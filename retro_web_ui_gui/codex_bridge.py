"""A GUI-independent bridge for the Codex App Server stdio JSONL protocol.

The app-server protocol is deliberately contained here so a desktop shell only
needs to consume stable :class:`BridgeEvent` objects and issue high-level
operations.  It uses only the Python standard library and does not store
credentials; authentication remains owned by the user's Codex installation.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union


class BridgeError(RuntimeError):
    """Base error raised by the bridge."""


class BridgeUnavailableError(BridgeError):
    """Raised when the Codex executable cannot be started."""


class BridgeProtocolError(BridgeError):
    """Raised for a JSON-RPC error response from app-server."""

    def __init__(self, method: str, error: Mapping[str, Any]):
        self.method = method
        self.code = error.get("code")
        self.details = dict(error)
        super().__init__(f"{method} failed ({self.code}): {error.get('message', 'unknown protocol error')}")


class BridgeTimeoutError(BridgeError):
    """Raised when app-server does not answer a request in time."""


class BridgeState(str, Enum):
    NEW = "new"
    STARTING = "starting"
    READY = "ready"
    STOPPED = "stopped"
    EXITED = "exited"


@dataclass(frozen=True)
class CodexAvailability:
    available: bool
    executable: Optional[str]
    version: Optional[str]
    error: Optional[str] = None


@dataclass(frozen=True)
class BridgeEvent:
    """A redacted, application-facing event derived from app-server traffic."""

    kind: str
    data: Mapping[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ApprovalRequest:
    """A pending server-initiated approval request safe for direct GUI display."""

    request_id: Union[int, str]
    method: str
    kind: str
    thread_id: Optional[str]
    turn_id: Optional[str]
    item_id: Optional[str]
    command: Optional[Sequence[str]]
    cwd: Optional[str]
    reason: Optional[str]
    available_decisions: Tuple[str, ...]
    details: Mapping[str, Any]


@dataclass
class _PendingResponse:
    method: str
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: Optional[Mapping[str, Any]] = None


_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|authorization|bearer|secret|password|auth[_-]?url|verification[_-]?url|user[_-]?code)",
    re.I,
)
_TOKEN_VALUE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+[^\s]+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b",
    re.I,
)


def redact_secrets(value: Any) -> Any:
    """Return a copy appropriate for diagnostics and event history.

    Protocol responses themselves are retained only long enough to resolve the
    caller's request.  Events and errors use this function so tokens cannot
    leak into GUI logs.
    """

    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _TOKEN_VALUE.sub("[REDACTED]", value)
    return value


class CodexBridge:
    """Owns one ``codex app-server`` stdio subprocess.

    A bridge instance is intentionally scoped to one GUI session.  It does not
    mutate Codex configuration and it never owns authentication credentials.
    ``process_factory`` is injectable for deterministic contract tests.
    """

    def __init__(
        self,
        executable: str = "codex",
        *,
        client_name: str = "retro_web_ui_gui",
        client_title: str = "Retro Web UI GUI",
        client_version: str = "0.0.0",
        process_factory: Optional[Callable[..., Any]] = None,
        version_runner: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.executable = executable
        self.client_info = {"name": client_name, "title": client_title, "version": client_version}
        self._process_factory = process_factory or subprocess.Popen
        self._version_runner = version_runner or subprocess.run
        self._process: Any = None
        self._state = BridgeState.NEW
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._next_id = 1
        self._pending: Dict[Union[int, str], _PendingResponse] = {}
        self._events: List[BridgeEvent] = []
        self._listeners: List[Callable[[BridgeEvent], None]] = []
        self._approvals: Dict[Union[int, str], ApprovalRequest] = {}
        self._latest_diffs: Dict[Tuple[Optional[str], Optional[str]], Any] = {}
        self._active_turns: Dict[str, str] = {}
        self._reader_threads: List[threading.Thread] = []
        self._initialized = False
        self._shutdown_requested = False
        self._stderr_tail: List[str] = []

    @property
    def state(self) -> BridgeState:
        with self._lock:
            return self._state

    @property
    def events(self) -> Tuple[BridgeEvent, ...]:
        with self._lock:
            return tuple(self._events)

    @property
    def pending_approvals(self) -> Tuple[ApprovalRequest, ...]:
        with self._lock:
            return tuple(self._approvals.values())

    @classmethod
    def detect(
        cls,
        executable: str = "codex",
        *,
        timeout: float = 5.0,
        forbidden_roots: Sequence[Path] = (),
    ) -> CodexAvailability:
        """Detect a usable CLI and report its version without starting a session."""

        resolved = cls.resolve_executable(executable, forbidden_roots=forbidden_roots)
        if not resolved:
            return CodexAvailability(False, None, None, f"Codex executable not found: {executable}")
        try:
            completed = subprocess.run(
                [resolved, "--version"], capture_output=True, text=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.SubprocessError) as error:
            return CodexAvailability(False, resolved, None, str(error))
        if completed.returncode != 0:
            return CodexAvailability(False, resolved, None, redact_secrets(completed.stderr.strip() or completed.stdout.strip()))
        return CodexAvailability(True, resolved, completed.stdout.strip() or None)

    @staticmethod
    def resolve_executable(executable: str, *, forbidden_roots: Sequence[Path] = ()) -> Optional[str]:
        """Resolve Codex without assuming a desktop app inherits shell ``PATH``.

        A bare name is never resolved from the current project directory. This
        prevents an untrusted repository-local ``codex`` file from shadowing
        the user's installed launcher.
        """
        requested = Path(executable).expanduser()
        forbidden = tuple(Path(root).expanduser().resolve() for root in forbidden_roots)
        contains_separator = os.sep in executable or bool(os.altsep and os.altsep in executable)
        if contains_separator or requested.is_absolute():
            resolved_request = requested.resolve()
            if (
                requested.is_absolute()
                and CodexBridge._is_launchable(resolved_request)
                and not CodexBridge._is_within_any(resolved_request, forbidden)
            ):
                return str(resolved_request)
            return None
        trusted_path = CodexBridge._absolute_search_path()
        discovered = shutil.which(executable, path=trusted_path) if trusted_path else None
        if discovered:
            discovered_path = Path(discovered).resolve()
            blocked_roots = (Path.cwd(), *forbidden)
            if CodexBridge._is_launchable(discovered_path) and not CodexBridge._is_within_any(
                discovered_path, blocked_roots
            ):
                return str(discovered_path)
        if requested.name.casefold() not in {"codex", "codex.exe", "codex.cmd"}:
            return None
        # These are bounded install locations rather than PATH-derived paths.
        # Do not reject them merely because Finder launched with the user's
        # home as cwd; selected project roots remain forbidden.
        for candidate in CodexBridge.fallback_executable_candidates():
            resolved_candidate = candidate.resolve()
            if CodexBridge._is_launchable(resolved_candidate) and not CodexBridge._is_within_any(
                resolved_candidate, forbidden
            ):
                return str(resolved_candidate)
        return None

    @staticmethod
    def _absolute_search_path() -> Optional[str]:
        """Drop empty, current-directory, and relative PATH entries."""
        entries = []
        for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
            expanded = os.path.expanduser(entry.strip().strip('"'))
            if expanded and os.path.isabs(expanded):
                entries.append(expanded)
        return os.pathsep.join(entries) or None

    @staticmethod
    def _is_launchable(candidate: Path) -> bool:
        return candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK))

    @staticmethod
    def _is_within_any(candidate: Path, roots: Sequence[Path]) -> bool:
        for root in roots:
            try:
                candidate.relative_to(Path(root).expanduser().resolve())
                return True
            except ValueError:
                continue
        return False

    @staticmethod
    def fallback_executable_candidates() -> Tuple[Path, ...]:
        """Return bounded official/common install locations for GUI launches."""
        home = Path.home()
        if sys.platform == "darwin":
            applications = (Path("/Applications"), home / "Applications")
            app_resources = tuple(
                root / app / "Contents" / "Resources" / "codex"
                for root in applications
                for app in ("ChatGPT.app", "Codex.app")
            )
            return app_resources + (
                Path("/opt/homebrew/bin/codex"),
                Path("/usr/local/bin/codex"),
                home / ".local" / "bin" / "codex",
                home / ".npm-global" / "bin" / "codex",
            )
        if sys.platform.startswith("win"):
            candidates: list[Path] = []
            appdata = os.environ.get("APPDATA")
            local_appdata = os.environ.get("LOCALAPPDATA")
            if appdata:
                candidates.append(Path(appdata) / "npm" / "codex.cmd")
            if local_appdata:
                candidates.extend(
                    [
                        Path(local_appdata) / "Programs" / "ChatGPT" / "resources" / "codex.exe",
                        Path(local_appdata) / "Programs" / "Codex" / "resources" / "codex.exe",
                    ]
                )
            return tuple(candidates)
        return (
            home / ".local" / "bin" / "codex",
            home / ".npm-global" / "bin" / "codex",
            Path("/usr/local/bin/codex"),
            Path("/snap/bin/codex"),
        )

    def add_listener(self, listener: Callable[[BridgeEvent], None]) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def remove() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return remove

    def start(self, *, cwd: Optional[Path] = None) -> Mapping[str, Any]:
        """Spawn app-server, perform the required initialize handshake, and return it."""

        with self._lock:
            if self._state is BridgeState.READY:
                raise BridgeError("CodexBridge is already running")
            if self._state is BridgeState.EXITED:
                raise BridgeError("CodexBridge exited; create a new bridge or call restart")
            self._state = BridgeState.STARTING
            self._shutdown_requested = False
        forbidden_roots = (cwd,) if cwd else ()
        resolved = self.resolve_executable(self.executable, forbidden_roots=forbidden_roots)
        if not resolved:
            with self._lock:
                self._state = BridgeState.EXITED
            raise BridgeUnavailableError(f"Codex executable could not be resolved safely: {self.executable}")
        try:
            self._process = self._process_factory(
                [resolved, "app-server"],
                cwd=str(cwd) if cwd else None,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as error:
            with self._lock:
                self._state = BridgeState.EXITED
            raise BridgeUnavailableError(f"Unable to start Codex App Server: {error}") from error

        self._start_reader(self._process.stdout, self._read_stdout, "codex-app-server-stdout")
        if getattr(self._process, "stderr", None) is not None:
            self._start_reader(self._process.stderr, self._read_stderr, "codex-app-server-stderr")

        try:
            initialization = self.request("initialize", {"clientInfo": self.client_info})
            self.notify("initialized", {})
        except Exception:
            self.shutdown(wait_seconds=0.1)
            raise
        with self._lock:
            self._initialized = True
            self._state = BridgeState.READY
        self._emit("ready", {"initialization": initialization})
        return initialization

    def restart(self, *, cwd: Optional[Path] = None) -> Mapping[str, Any]:
        """Start a fresh transport after an unexpected local process exit."""
        with self._lock:
            if self._state not in {BridgeState.EXITED, BridgeState.STOPPED}:
                raise BridgeError("CodexBridge can restart only after it stopped or exited")
            self._process = None
            self._state = BridgeState.NEW
            self._initialized = False
            self._shutdown_requested = False
            self._pending.clear()
            self._approvals.clear()
            self._active_turns.clear()
            self._reader_threads = []
        self._emit("restarting", {})
        return self.start(cwd=cwd)

    def request(self, method: str, params: Optional[Mapping[str, Any]] = None, *, timeout: float = 30.0) -> Any:
        """Send a JSON-RPC request and block until its correlated response arrives."""

        with self._lock:
            if self._process is None or self._state in {BridgeState.STOPPED, BridgeState.EXITED}:
                raise BridgeUnavailableError("Codex App Server is not running")
            request_id = self._next_id
            self._next_id += 1
            pending = _PendingResponse(method=method)
            self._pending[request_id] = pending
        try:
            self._send({"method": method, "id": request_id, "params": dict(params or {})})
            if not pending.event.wait(timeout):
                raise BridgeTimeoutError(f"Timed out waiting for {method}")
            if pending.error is not None:
                raise BridgeProtocolError(method, pending.error)
            return pending.result
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def notify(self, method: str, params: Optional[Mapping[str, Any]] = None) -> None:
        self._send({"method": method, "params": dict(params or {})})

    # Account and model discovery -------------------------------------------------
    def account_read(self, *, refresh_token: bool = False) -> Mapping[str, Any]:
        return self.request("account/read", {"refreshToken": refresh_token})

    def list_models(self, *, limit: int = 100, include_hidden: bool = False) -> Mapping[str, Any]:
        return self.request("model/list", {"limit": limit, "includeHidden": include_hidden})

    def read_configuration(self, *, cwd: Optional[Path] = None) -> Mapping[str, Any]:
        """Discover effective Codex configuration without modifying or logging it."""
        return self.request("config/read", {"cwd": str(cwd) if cwd else None, "includeLayers": False})

    def begin_chatgpt_login(self, *, device_code: bool = False) -> Mapping[str, Any]:
        login_type = "chatgptDeviceCode" if device_code else "chatgpt"
        params: Dict[str, Any] = {"type": login_type}
        if not device_code:
            params.update({"useHostedLoginSuccessPage": True, "appBrand": "codex"})
        return self.request("account/login/start", params)

    def cancel_login(self, login_id: str) -> Any:
        return self.request("account/login/cancel", {"loginId": login_id})

    # Thread and turn lifecycle ---------------------------------------------------
    def start_thread(self, **params: Any) -> Mapping[str, Any]:
        return self.request("thread/start", params)

    def resume_thread(self, thread_id: str, **params: Any) -> Mapping[str, Any]:
        payload = {"threadId": thread_id, **params}
        return self.request("thread/resume", payload)

    def read_thread(self, thread_id: str, *, include_turns: bool = True) -> Mapping[str, Any]:
        """Read durable server state after a reconnect without replaying a turn."""
        return self.request("thread/read", {"threadId": thread_id, "includeTurns": include_turns})

    def start_turn(
        self,
        thread_id: str,
        input_items: Iterable[Mapping[str, Any]],
        **overrides: Any,
    ) -> Mapping[str, Any]:
        payload = {"threadId": thread_id, "input": list(input_items), **overrides}
        result = self.request("turn/start", payload)
        turn = result.get("turn", {}) if isinstance(result, Mapping) else {}
        if turn.get("id"):
            with self._lock:
                self._active_turns[thread_id] = str(turn["id"])
        return result

    def steer_turn(self, thread_id: str, expected_turn_id: str, input_items: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
        return self.request(
            "turn/steer", {"threadId": thread_id, "expectedTurnId": expected_turn_id, "input": list(input_items)}
        )

    def interrupt_turn(self, thread_id: str, turn_id: Optional[str] = None) -> Any:
        with self._lock:
            selected_turn = turn_id or self._active_turns.get(thread_id)
        if not selected_turn:
            raise BridgeError(f"No active turn is known for thread {thread_id}")
        return self.request("turn/interrupt", {"threadId": thread_id, "turnId": selected_turn})

    def latest_diff(self, thread_id: Optional[str], turn_id: Optional[str]) -> Any:
        with self._lock:
            return self._latest_diffs.get((thread_id, turn_id))

    # Server-initiated approval requests -----------------------------------------
    def approve(self, request_id: Union[int, str], *, for_session: bool = False) -> None:
        with self._lock:
            approval = self._approvals.get(request_id)
        if approval and approval.kind == "permissions":
            requested = approval.details.get("permissions")
            permissions = requested if isinstance(requested, Mapping) else {}
            self._resolve_approval(
                request_id,
                {"permissions": permissions, "scope": "session" if for_session else "turn"},
            )
            return
        decision = "acceptForSession" if for_session else "accept"
        self._resolve_approval(request_id, {"decision": decision})

    def deny(self, request_id: Union[int, str], *, cancel: bool = False) -> None:
        with self._lock:
            approval = self._approvals.get(request_id)
        if approval and approval.kind == "permissions":
            self._resolve_approval(request_id, {"permissions": {}, "scope": "turn"})
            return
        self._resolve_approval(request_id, {"decision": "cancel" if cancel else "decline"})

    def answer_user_input(self, request_id: Union[int, str], answers: Mapping[str, Sequence[str]]) -> None:
        """Resolve a tool question using only GUI-authored answer strings."""
        with self._lock:
            approval = self._approvals.get(request_id)
            if approval is None or approval.kind != "user_input":
                raise BridgeError(f"No pending user input request {request_id}")
            self._approvals.pop(request_id, None)
        normalized = {
            str(question_id): {"answers": [str(value) for value in values]}
            for question_id, values in answers.items()
        }
        self._send({"id": request_id, "result": {"answers": normalized}})
        self._emit("user_input_resolved", {"requestId": request_id, "answered": sorted(normalized)})

    def _resolve_approval(self, request_id: Union[int, str], result: Mapping[str, Any]) -> None:
        with self._lock:
            if request_id not in self._approvals:
                raise BridgeError(f"No pending approval request {request_id}")
            self._approvals.pop(request_id, None)
        self._send({"id": request_id, "result": dict(result)})
        self._emit("approval_resolved", {"requestId": request_id, "decision": result.get("decision")})

    # Shutdown and low-level transport -------------------------------------------
    def shutdown(self, *, wait_seconds: float = 2.0) -> None:
        """Interrupt known active work, close stdio, then terminate if necessary."""

        with self._lock:
            process = self._process
            if process is None or self._state in {BridgeState.STOPPED, BridgeState.EXITED}:
                return
            self._shutdown_requested = True
            active_turns = tuple(self._active_turns.items())
        if self._initialized:
            for thread_id, turn_id in active_turns:
                try:
                    self.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=min(wait_seconds, 1.0))
                except BridgeError:
                    pass
        stdin = getattr(process, "stdin", None)
        if stdin is not None:
            try:
                stdin.close()
            except (OSError, ValueError):
                pass
        try:
            process.wait(timeout=wait_seconds)
        except (subprocess.TimeoutExpired, TimeoutError):
            try:
                process.terminate()
                process.wait(timeout=wait_seconds)
            except (subprocess.TimeoutExpired, TimeoutError):
                process.kill()
        with self._lock:
            self._state = BridgeState.STOPPED
            self._process = None
            self._initialized = False
        self._emit("stopped", {})

    def _send(self, message: Mapping[str, Any]) -> None:
        process = self._process
        stdin = getattr(process, "stdin", None) if process is not None else None
        if stdin is None:
            raise BridgeUnavailableError("Codex App Server stdin is unavailable")
        encoded = json.dumps(dict(message), separators=(",", ":")) + "\n"
        try:
            with self._write_lock:
                stdin.write(encoded)
                stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as error:
            self._mark_exited(f"App Server stdin closed: {error}")
            raise BridgeUnavailableError("Codex App Server connection closed") from error

    def _start_reader(self, stream: Any, reader: Callable[[Any], None], name: str) -> None:
        thread = threading.Thread(target=reader, args=(stream,), name=name, daemon=True)
        self._reader_threads.append(thread)
        thread.start()

    def _read_stdout(self, stream: Any) -> None:
        try:
            for line in iter(stream.readline, ""):
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self._emit("protocol_warning", {"message": "Invalid JSON from App Server", "line": line[:500]})
                    continue
                self._handle_message(message)
        finally:
            if not self._shutdown_requested:
                self._mark_exited("Codex App Server stdout closed")

    def _read_stderr(self, stream: Any) -> None:
        for line in iter(stream.readline, ""):
            redacted = str(redact_secrets(line.rstrip()))
            with self._lock:
                self._stderr_tail = (self._stderr_tail + [redacted])[-20:]
            self._emit("stderr", {"line": redacted})

    def _handle_message(self, message: Mapping[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            request_id = message["id"]
            if not isinstance(request_id, (int, str)) or isinstance(request_id, bool):
                self._emit("protocol_warning", {"message": "Invalid response id"})
                return
            with self._lock:
                pending = self._pending.get(request_id)
            if pending:
                pending.result = message.get("result")
                error = message.get("error")
                pending.error = redact_secrets(error) if isinstance(error, Mapping) else None
                pending.event.set()
            else:
                self._emit("orphan_response", {"id": request_id, "message": redact_secrets(message)})
            return

        if "id" in message and "method" in message:
            self._handle_server_request(message)
            return
        if "method" in message:
            self._handle_notification(str(message["method"]), message.get("params") or {})
            return
        self._emit("protocol_warning", {"message": "Unrecognised JSON-RPC message", "payload": redact_secrets(message)})

    def _handle_server_request(self, message: Mapping[str, Any]) -> None:
        request_id = message["id"]
        if not isinstance(request_id, (int, str)) or isinstance(request_id, bool):
            self._emit("protocol_warning", {"message": "Invalid server request id"})
            return
        method = str(message["method"])
        params = message.get("params") or {}
        supported = {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
            "item/tool/requestUserInput",
        }
        if method not in supported:
            # Every server request must receive a correlated response. Leaving
            # an unknown request unresolved would stall the agent indefinitely.
            self._send({
                "id": request_id,
                "error": {"code": -32601, "message": "This GUI does not support the requested client operation."},
            })
            self._emit("server_request", {"id": request_id, "method": method, "params": redact_secrets(params)})
            return
        if not isinstance(params, Mapping):
            self._emit("protocol_warning", {"message": "Malformed approval request", "method": method})
            return
        command = params.get("command")
        if isinstance(command, str):
            command = (command,)
        elif isinstance(command, list):
            command = tuple(str(piece) for piece in command)
        else:
            command = None
        if method == "item/tool/requestUserInput":
            approval = ApprovalRequest(
                request_id=request_id,
                method=method,
                kind="user_input",
                thread_id=_optional_string(params.get("threadId")),
                turn_id=_optional_string(params.get("turnId")),
                item_id=_optional_string(params.get("itemId")),
                command=None,
                cwd=None,
                reason=None,
                available_decisions=(),
                details=redact_secrets(params),
            )
            with self._lock:
                self._approvals[request_id] = approval
            self._emit("user_input_requested", {"requestId": request_id, "details": approval.details})
            return
        kind = (
            "command" if "commandExecution" in method
            else "permissions" if "permissions" in method
            else "file_change"
        )
        approval = ApprovalRequest(
            request_id=request_id,
            method=method,
            kind=kind,
            thread_id=_optional_string(params.get("threadId")),
            turn_id=_optional_string(params.get("turnId")),
            item_id=_optional_string(params.get("itemId")),
            command=command,
            cwd=_optional_string(params.get("cwd")),
            reason=_optional_string(params.get("reason")),
            available_decisions=tuple(str(value) for value in params.get("availableDecisions", ())),
            details=redact_secrets(params),
        )
        with self._lock:
            self._approvals[request_id] = approval
        self._emit("approval_requested", {"approval": _approval_as_dict(approval)})

    def _handle_notification(self, method: str, params: Any) -> None:
        if not isinstance(params, Mapping):
            params = {"value": params}
        event_kind = {
            "item/agentMessage/delta": "agent_message_delta",
            "item/started": "item_started",
            "item/completed": "item_completed",
            "turn/started": "turn_started",
            "turn/completed": "turn_completed",
            "turn/diff/updated": "diff_updated",
            "turn/plan/updated": "plan_updated",
            "thread/status/changed": "thread_status",
            "serverRequest/resolved": "server_request_resolved",
            "account/updated": "account_updated",
            "account/login/completed": "login_completed",
            "warning": "warning",
            "configWarning": "config_warning",
        }.get(method, "notification")
        if method == "turn/diff/updated":
            key = (_optional_string(params.get("threadId")), _optional_string(params.get("turnId")))
            with self._lock:
                self._latest_diffs[key] = params.get("diff")
        if method == "turn/started":
            turn = params.get("turn")
            thread_id = _optional_string(params.get("threadId"))
            if isinstance(turn, Mapping):
                thread_id = _optional_string(turn.get("threadId")) or thread_id
            if isinstance(turn, Mapping) and thread_id and turn.get("id"):
                with self._lock:
                    self._active_turns[thread_id] = str(turn["id"])
        if method == "turn/completed":
            turn = params.get("turn")
            if isinstance(turn, Mapping):
                thread_id = _optional_string(turn.get("threadId")) or _optional_string(params.get("threadId"))
                if thread_id:
                    with self._lock:
                        self._active_turns.pop(thread_id, None)
        self._emit(event_kind, {"method": method, "params": redact_secrets(params)})

    def _mark_exited(self, reason: str) -> None:
        with self._lock:
            if self._state in {BridgeState.STOPPED, BridgeState.EXITED}:
                return
            self._state = BridgeState.EXITED
            pending = tuple(self._pending.values())
            process = self._process
            exit_code = process.poll() if process is not None and hasattr(process, "poll") else None
        error = {"code": "APP_SERVER_EXITED", "message": reason, "exitCode": exit_code}
        for waiting in pending:
            waiting.error = error
            waiting.event.set()
        self._emit("unexpected_exit", {"reason": reason, "exitCode": exit_code, "stderrTail": tuple(self._stderr_tail)})

    def _emit(self, kind: str, data: Mapping[str, Any]) -> None:
        event = BridgeEvent(kind=kind, data=redact_secrets(data))
        with self._lock:
            # Long-running turns can produce thousands of deltas.  The GUI has
            # its own presentation history; retaining a bounded diagnostic tail
            # prevents the protocol adapter from growing without limit.
            self._events = (self._events + [event])[-5000:]
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                # A UI observer must never tear down the protocol reader.
                pass


def _optional_string(value: Any) -> Optional[str]:
    return str(value) if value is not None else None


def _approval_as_dict(approval: ApprovalRequest) -> Mapping[str, Any]:
    return {
        "requestId": approval.request_id,
        "method": approval.method,
        "kind": approval.kind,
        "threadId": approval.thread_id,
        "turnId": approval.turn_id,
        "itemId": approval.item_id,
        "command": approval.command,
        "cwd": approval.cwd,
        "reason": approval.reason,
        "availableDecisions": approval.available_decisions,
        "details": approval.details,
    }
