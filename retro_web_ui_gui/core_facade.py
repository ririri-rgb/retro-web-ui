"""Safe, GUI-oriented access to the canonical Retro Web UI CLI contract.

The installed/frozen desktop uses the exact CLI parser and handlers in-process;
source checkouts may still inject a CLI path for process-isolation tests.  Both
routes return the same versioned JSON envelope and neither duplicates detector,
audit, theme, behavior, or verification logic in the GUI package.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import redirect_stderr, redirect_stdout
import io
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Iterable, Optional


class CliFacadeError(RuntimeError):
    """A safe application-facing error; stderr is retained separately."""


class CliUnavailableError(CliFacadeError):
    pass


class CliProtocolError(CliFacadeError):
    pass


class ScopeError(CliFacadeError):
    pass


@dataclass(frozen=True)
class CliResponse:
    document: dict[str, Any]
    returncode: int
    stderr: str

    @property
    def status(self) -> str:
        return str(self.document["status"])

    @property
    def result(self) -> Any:
        return self.document["result"]

    @property
    def diagnostics(self) -> list[dict[str, Any]]:
        return list(self.document["diagnostics"])


@dataclass(frozen=True)
class GitState:
    available: bool
    repository: bool
    root: Optional[Path]
    dirty: bool
    entries: tuple[str, ...]


@dataclass(frozen=True)
class DiffSummary:
    available: bool
    files: tuple[str, ...]
    stat: str
    patch: str = ""
    untracked: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    cwd: Path
    returncode: Optional[int]
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


_IN_PROCESS_CLI_LOCK = threading.Lock()


class CoreFacade:
    """Controlled facade for the canonical bundled CLI.

    The GUI should retain returned documents rather than infer additional
    success semantics from exit codes alone: an exit code of one is an
    intentional, structured review state.
    """

    def __init__(
        self,
        *,
        cli_path: Optional[Path] = None,
        python_executable: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if cli_path is not None:
            self.cli_path = cli_path.resolve()
        elif importlib.util.find_spec("retro_web_ui") is None:
            # A raw source checkout has a hyphenated Skill directory and relies
            # on the legacy script entry point. Installed/frozen distributions
            # expose the same files as the importable ``retro_web_ui`` package.
            self.cli_path = (_repository_root() / "skills" / "retro-web-ui" / "scripts" / "retro_web_ui.py").resolve()
        else:
            self.cli_path = None
        self.python_executable = python_executable or sys.executable
        self.timeout_seconds = timeout_seconds

    @property
    def skill_path(self) -> Path:
        """Return the Skill entry point from the same installed CLI package."""
        if self.cli_path is not None:
            return self.cli_path.parents[1] / "SKILL.md"
        import retro_web_ui

        return Path(retro_web_ui.__file__).resolve().parent / "SKILL.md"

    def _run(self, arguments: Iterable[str]) -> CliResponse:
        values = tuple(map(str, arguments))
        if self.cli_path is None:
            return self._run_in_process(values)
        if not self.cli_path.is_file():
            raise CliUnavailableError(f"Bundled Retro Web UI CLI is unavailable: {self.cli_path}")
        argv = [self.python_executable, str(self.cli_path), *values, "--json"]
        try:
            completed = subprocess.run(
                argv,
                cwd=str(_repository_root()),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CliUnavailableError(f"Could not start bundled Retro Web UI CLI: {error}") from error
        try:
            document = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise CliProtocolError("Bundled Retro Web UI CLI did not return one valid JSON envelope.") from error
        self._validate_envelope(document)
        return CliResponse(document=document, returncode=completed.returncode, stderr=completed.stderr)

    def _run_in_process(self, arguments: tuple[str, ...]) -> CliResponse:
        """Invoke the packaged CLI unchanged, including its parser/error boundary.

        ``redirect_stdout`` is process-global, so calls are serialized.  The GUI
        currently runs deterministic analysis sequentially; the lock also keeps
        future worker-thread use from interleaving envelopes.
        """
        try:
            from retro_web_ui.scripts import retro_web_ui as cli
        except ImportError as error:
            raise CliUnavailableError(f"Bundled Retro Web UI CLI is unavailable: {error}") from error
        stdout = io.StringIO()
        stderr = io.StringIO()
        with _IN_PROCESS_CLI_LOCK, redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = cli.main([*arguments, "--json"])
        try:
            document = json.loads(stdout.getvalue())
        except json.JSONDecodeError as error:
            raise CliProtocolError("Bundled Retro Web UI CLI did not return one valid JSON envelope.") from error
        self._validate_envelope(document)
        return CliResponse(document=document, returncode=returncode, stderr=stderr.getvalue())

    @staticmethod
    def _validate_envelope(document: Any) -> None:
        if not isinstance(document, dict):
            raise CliProtocolError("CLI response is not a JSON object.")
        required = {"schema_version", "tool", "command", "status", "result", "diagnostics", "meta"}
        if not required.issubset(document):
            raise CliProtocolError("CLI response is missing required envelope fields.")
        tool = document["tool"]
        if document["schema_version"] != 1 or not isinstance(tool, dict) or tool.get("name") != "retro-web-ui":
            raise CliProtocolError("CLI response does not match the Retro Web UI JSON contract.")
        if not isinstance(document["diagnostics"], list) or not isinstance(document["meta"], dict):
            raise CliProtocolError("CLI response has malformed diagnostics or metadata.")

    @staticmethod
    def project_root(value: Path | str) -> Path:
        raw = Path(value).expanduser()
        if raw.is_symlink():
            raise ScopeError(f"Project root may not be a symlink: {raw}")
        root = raw.resolve()
        if not root.is_dir():
            raise ScopeError(f"Project root is not a readable directory: {root}")
        return root

    @staticmethod
    def contained_path(root: Path, value: Path | str, *, require_directory: bool = False) -> Path:
        """Resolve a selected path while rejecting symlink traversal/outside roots."""
        root = CoreFacade.project_root(root)
        raw = Path(value)
        candidate = raw if raw.is_absolute() else root / raw
        current = candidate
        while current != root:
            if current.is_symlink():
                raise ScopeError(f"Selected path traverses a symlink: {current}")
            if current.parent == current:
                break
            current = current.parent
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise ScopeError(f"Selected path is outside project root: {resolved}") from error
        if require_directory and not resolved.is_dir():
            raise ScopeError(f"Selected application is not a directory: {resolved}")
        return resolved

    def info(self) -> CliResponse:
        return self._run(("info",))

    def analyze(self, root: Path | str, app: Optional[str] = None) -> CliResponse:
        args = ["analyze", str(self.project_root(root))]
        if app:
            args.extend(("--app", app))
        return self._run(args)

    def doctor(self, root: Path | str, app: Optional[str] = None) -> CliResponse:
        args = ["doctor", str(self.project_root(root))]
        if app:
            args.extend(("--app", app))
        return self._run(args)

    def theme_list(self) -> CliResponse:
        return self._run(("theme", "list"))

    def theme_bundle(self, theme: str) -> CliResponse:
        """Return the canonical deterministic bundle without writing a target file."""
        return self._run(("theme", "bundle", theme))

    def snapshot(self, root: Path | str, output: Path | str) -> CliResponse:
        project = self.project_root(root)
        destination = Path(output).expanduser()
        if destination.is_symlink():
            raise ScopeError(f"Baseline output may not be a symlink: {destination}")
        resolved = destination.resolve()
        try:
            resolved.relative_to(project)
        except ValueError:
            pass
        else:
            raise ScopeError("Baseline must be outside the selected project.")
        return self._run(("behavior", "snapshot", str(project), "--output", str(resolved)))

    def compare(self, baseline: Path | str, root: Path | str) -> CliResponse:
        return self._run(("behavior", "compare", str(Path(baseline).resolve()), str(self.project_root(root))))

    def audit(self, root: Path | str, theme: str) -> CliResponse:
        return self._run(("audit", str(self.project_root(root)), "--theme", theme))

    def verify(self, root: Path | str, *, app: Optional[str], theme: str, baseline: Path | str) -> CliResponse:
        args = ["verify", str(self.project_root(root)), "--theme", theme, "--baseline", str(Path(baseline).resolve())]
        if app:
            args.extend(("--app", app))
        return self._run(args)

    def create_external_baseline(self, root: Path | str) -> tuple[Path, CliResponse]:
        directory = Path(tempfile.mkdtemp(prefix="retro-web-ui-baseline-"))
        output = directory / "behavior-baseline.json"
        return output, self.snapshot(root, output)

    def git_state(self, root: Path | str) -> GitState:
        project = self.project_root(root)
        try:
            probe = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return GitState(False, False, None, False, ())
        if probe.returncode:
            return GitState(True, False, None, False, ())
        git_root = Path(probe.stdout.strip()).resolve()
        status = subprocess.run(
            ["git", "-C", str(project), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        entries = tuple(line for line in status.stdout.splitlines() if line) if not status.returncode else ()
        return GitState(True, True, git_root, bool(entries), entries)

    def diff_summary(self, root: Path | str) -> DiffSummary:
        project = self.project_root(root)
        state = self.git_state(project)
        if not state.repository:
            return DiffSummary(False, (), "")
        try:
            names = subprocess.run(
                ["git", "-C", str(project), "--no-pager", "diff", "--no-ext-diff", "--name-only", "HEAD"],
                capture_output=True, text=True, check=False, timeout=10,
            )
            stat = subprocess.run(
                ["git", "-C", str(project), "--no-pager", "diff", "--no-ext-diff", "--stat", "HEAD"],
                capture_output=True, text=True, check=False, timeout=10,
            )
            patch = subprocess.run(
                ["git", "-C", str(project), "--no-pager", "diff", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/", "HEAD"],
                capture_output=True, text=True, check=False, timeout=10,
            )
            untracked = subprocess.run(
                ["git", "-C", str(project), "ls-files", "--others", "--exclude-standard"],
                capture_output=True, text=True, check=False, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return DiffSummary(False, (), "")
        untracked_files = tuple(line for line in untracked.stdout.splitlines() if line) if untracked.returncode == 0 else ()
        files = tuple(dict.fromkeys([*(line for line in names.stdout.splitlines() if line), *untracked_files]))
        available = names.returncode == 0 and stat.returncode == 0 and patch.returncode == 0
        return DiffSummary(available, files, stat.stdout, patch.stdout[:2_000_000], untracked_files)

    def run_verification_command(
        self,
        project_root: Path | str,
        working_directory: Path | str,
        argv: Iterable[str],
        *,
        authorized: bool,
        timeout_seconds: float = 300.0,
    ) -> CommandResult:
        """Run one reviewed CLI verification-plan entry without a shell.

        Callers must pass ``authorized=True`` only after displaying the exact
        argv and cwd to the user.  This method does not install dependencies or
        infer commands; it only executes the already reviewed plan.
        """
        if not authorized:
            raise PermissionError("Verification command requires explicit user authorization.")
        root = self.project_root(project_root)
        cwd = self.contained_path(root, working_directory, require_directory=True)
        command = tuple(str(part) for part in argv)
        if not command or not command[0]:
            raise ValueError("Verification command argv may not be empty.")
        started = time.monotonic()
        try:
            completed = subprocess.run(
                list(command),
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
            stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
            return CommandResult(command, cwd, None, stdout[-500_000:], stderr[-500_000:], time.monotonic() - started, True)
        except OSError as error:
            return CommandResult(command, cwd, None, "", str(error), time.monotonic() - started, False)
        return CommandResult(
            command,
            cwd,
            completed.returncode,
            completed.stdout[-500_000:],
            completed.stderr[-500_000:],
            time.monotonic() - started,
            False,
        )
