"""GUI-independent state machine for a safe Retro Web UI conversion workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import shutil
import tempfile
from typing import Any, Optional

from .core_facade import CliResponse, CommandResult, CoreFacade, DiffSummary, GitState


class WorkflowState(str, Enum):
    NEW = "new"
    APP_SELECTION_REQUIRED = "app_selection_required"
    READY_FOR_BASELINE = "ready_for_baseline"
    BASELINE_READY = "baseline_ready"
    AGENT_RUNNING = "agent_running"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    REVIEW_REQUIRED = "review_required"
    VERIFICATION_FAILED = "verification_failed"
    BEHAVIOR_INCOMPATIBILITY = "behavior_incompatibility"
    AGENT_INTERRUPTED = "agent_interrupted"
    ERROR = "error"
    CANCELLED = "cancelled"


class ResultClassification(str, Enum):
    COMPLETE = "complete"
    COMPLETE_WITH_REVIEW_ITEMS = "complete_with_review_items"
    REVIEW_REQUIRED = "review_required"
    VERIFICATION_FAILED = "verification_failed"
    BEHAVIOR_INCOMPATIBILITY = "behavior_incompatibility"
    AGENT_INTERRUPTED = "agent_interrupted"
    UNSUPPORTED = "unsupported_manual_intervention_required"


@dataclass(frozen=True)
class VerificationApproval:
    identifier: int
    purpose: str
    working_directory: Path
    argv: tuple[str, ...]
    reason: str
    risk: str
    status: str = "pending"


@dataclass
class WorkflowSnapshot:
    state: WorkflowState
    classification: Optional[ResultClassification]
    project_root: Optional[Path]
    selected_app: Optional[str]
    selected_theme: Optional[str]
    baseline: Optional[Path]
    git: Optional[GitState]
    diff: Optional[DiffSummary]
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    approvals: list[VerificationApproval] = field(default_factory=list)


class ConversionWorkflow:
    """State holder consumed by the desktop UI and the Codex integration layer.

    It intentionally stops at `agent_running`: session/message/event handling is
    owned by CodexBridge.  The bridge reports completion or interruption back
    here; deterministic evidence always comes from :class:`CoreFacade`.
    """

    def __init__(self, facade: CoreFacade) -> None:
        self.facade = facade
        self.state = WorkflowState.NEW
        self.classification: Optional[ResultClassification] = None
        self.project_root: Optional[Path] = None
        self.selected_app: Optional[str] = None
        self.selected_theme: Optional[str] = None
        self.baseline: Optional[Path] = None
        self.info: Optional[CliResponse] = None
        self.analysis: Optional[CliResponse] = None
        self.doctor: Optional[CliResponse] = None
        self.verification: Optional[CliResponse] = None
        self.git: Optional[GitState] = None
        self.diff: Optional[DiffSummary] = None
        self.diagnostics: list[dict[str, Any]] = []
        self.approvals: list[VerificationApproval] = []
        self.command_results: list[CommandResult] = []

    def snapshot(self) -> WorkflowSnapshot:
        return WorkflowSnapshot(self.state, self.classification, self.project_root, self.selected_app, self.selected_theme, self.baseline, self.git, self.diff, list(self.diagnostics), list(self.approvals))

    def prepare(self, project_root: Path | str) -> WorkflowSnapshot:
        self.project_root = self.facade.project_root(project_root)
        self.info = self.facade.info()
        if self.info.status != "ok" or not self.info.result.get("manifest_compatible", False):
            return self._fail(WorkflowState.ERROR, ResultClassification.UNSUPPORTED, self.info.diagnostics)
        self.git = self.facade.git_state(self.project_root)
        return self._refresh_analysis()

    def select_application(self, app: str) -> WorkflowSnapshot:
        self._require_project()
        selected = self.facade.contained_path(self.project_root, app, require_directory=True)
        self.selected_app = selected.relative_to(self.project_root).as_posix() or "."
        return self._refresh_analysis()

    def select_theme(self, theme: str) -> WorkflowSnapshot:
        response = self.facade.theme_list()
        available = {item["id"] for item in response.result["themes"]}
        if theme not in available:
            raise ValueError(f"Unsupported Retro Web UI theme: {theme}")
        self.selected_theme = theme
        return self.snapshot()

    def create_baseline(self) -> WorkflowSnapshot:
        self._require_ready_for_baseline()
        self.baseline, response = self.facade.create_external_baseline(self.project_root)
        self.diagnostics = response.diagnostics
        if response.status != "ok":
            return self._fail(WorkflowState.ERROR, ResultClassification.VERIFICATION_FAILED, response.diagnostics)
        self.state = WorkflowState.BASELINE_READY
        return self.snapshot()

    def begin_agent_conversion(self) -> WorkflowSnapshot:
        if self.state != WorkflowState.BASELINE_READY:
            raise RuntimeError("A compatible analysis, theme, and baseline are required before starting Codex.")
        self.state = WorkflowState.AGENT_RUNNING
        return self.snapshot()

    def agent_interrupted(self) -> WorkflowSnapshot:
        self.state = WorkflowState.AGENT_INTERRUPTED
        self.classification = ResultClassification.AGENT_INTERRUPTED
        self.diff = self.facade.diff_summary(self._require_project())
        return self.snapshot()

    def verification_approvals(self) -> list[VerificationApproval]:
        return list(self.approvals)

    def set_verification_approval(self, identifier: int, allowed: bool) -> WorkflowSnapshot:
        for index, item in enumerate(self.approvals):
            if item.identifier == identifier:
                self.approvals[index] = VerificationApproval(
                    item.identifier,
                    item.purpose,
                    item.working_directory,
                    item.argv,
                    item.reason,
                    item.risk,
                    "allowed" if allowed else "denied",
                )
                return self.snapshot()
        raise KeyError(f"Unknown verification approval: {identifier}")

    def run_authorized_verification(self, identifier: int, *, timeout_seconds: float = 300.0) -> CommandResult:
        """Execute exactly one user-approved target-native verification plan."""
        project = self._require_project()
        item = next((approval for approval in self.approvals if approval.identifier == identifier), None)
        if item is None:
            raise KeyError(f"Unknown verification approval: {identifier}")
        if item.status != "allowed":
            raise PermissionError("Verification command was not allowed by the user.")
        result = self.facade.run_verification_command(
            project,
            item.working_directory,
            item.argv,
            authorized=True,
            timeout_seconds=timeout_seconds,
        )
        self.command_results.append(result)
        return result

    def verify(self) -> WorkflowSnapshot:
        if self.state not in {WorkflowState.BASELINE_READY, WorkflowState.AGENT_RUNNING, WorkflowState.AGENT_INTERRUPTED}:
            raise RuntimeError("Verification requires a prepared baseline.")
        self.state = WorkflowState.VERIFYING
        response = self.facade.verify(self._require_project(), app=self.selected_app, theme=self._require_theme(), baseline=self._require_baseline())
        self.verification = response
        self.diagnostics = response.diagnostics
        self.diff = self.facade.diff_summary(self.project_root)
        behavior = response.result.get("behavior") if isinstance(response.result, dict) else None
        if isinstance(behavior, dict) and behavior.get("status") == "incompatible-baseline":
            return self._fail(WorkflowState.BEHAVIOR_INCOMPATIBILITY, ResultClassification.BEHAVIOR_INCOMPATIBILITY, response.diagnostics)
        # The behavior guard is deliberately conservative. Changed protected
        # hashes require review, but do not by themselves prove incompatible
        # runtime behavior. Only an incompatible baseline contract or a
        # confirmed runtime regression receives the stronger classification.
        behavior_review = isinstance(behavior, dict) and bool(behavior.get("protected_signal_changes"))
        if any(result.timed_out or result.returncode != 0 for result in self.command_results):
            return self._fail(WorkflowState.VERIFICATION_FAILED, ResultClassification.VERIFICATION_FAILED, response.diagnostics)
        if response.status == "ok":
            pending = [approval for approval in self.approvals if approval.status == "pending"]
            denied = [approval for approval in self.approvals if approval.status == "denied"]
            allowed = [approval for approval in self.approvals if approval.status == "allowed"]
            if pending or len(self.command_results) < len(allowed):
                self.state = WorkflowState.REVIEW_REQUIRED
                self.classification = ResultClassification.REVIEW_REQUIRED
            elif denied:
                self.state = WorkflowState.REVIEW_REQUIRED
                self.classification = ResultClassification.COMPLETE_WITH_REVIEW_ITEMS
            else:
                self.state = WorkflowState.COMPLETE
                self.classification = ResultClassification.COMPLETE
        elif response.status == "review_required" or behavior_review:
            self.state = WorkflowState.REVIEW_REQUIRED
            self.classification = ResultClassification.REVIEW_REQUIRED
        else:
            self.state = WorkflowState.VERIFICATION_FAILED
            self.classification = ResultClassification.VERIFICATION_FAILED
        return self.snapshot()

    def apply_agent_assessment(self, assessment: Optional[dict[str, Any]]) -> WorkflowSnapshot:
        """Merge semantic review evidence without letting it override harder failures.

        Deterministic verification cannot prove visual/runtime completeness.  A
        missing or review-bearing structured Codex result therefore downgrades
        an otherwise complete run, while deterministic behavior/build failures
        always remain authoritative.
        """
        if self.classification in {
            ResultClassification.VERIFICATION_FAILED,
            ResultClassification.BEHAVIOR_INCOMPATIBILITY,
            ResultClassification.AGENT_INTERRUPTED,
        }:
            return self.snapshot()
        if not isinstance(assessment, dict):
            self.state = WorkflowState.REVIEW_REQUIRED
            self.classification = ResultClassification.REVIEW_REQUIRED
            return self.snapshot()
        declared = str(assessment.get("classification") or "review_required")
        review_items = assessment.get("reviewItems")
        unavailable = assessment.get("verificationUnavailable")
        has_review_items = isinstance(review_items, list) and any(str(item).strip() for item in review_items)
        has_unavailable = isinstance(unavailable, list) and any(str(item).strip() for item in unavailable)
        if declared == "unsupported":
            self.state = WorkflowState.REVIEW_REQUIRED
            self.classification = ResultClassification.UNSUPPORTED
        elif declared == "review_required":
            self.state = WorkflowState.REVIEW_REQUIRED
            self.classification = ResultClassification.REVIEW_REQUIRED
        elif declared == "complete_with_review_items" or has_review_items or has_unavailable:
            self.state = WorkflowState.REVIEW_REQUIRED
            self.classification = ResultClassification.COMPLETE_WITH_REVIEW_ITEMS
        return self.snapshot()

    def mark_behavior_incompatible(self, diagnostics: Optional[list[dict[str, Any]]] = None) -> WorkflowSnapshot:
        """Record a confirmed runtime/contract behavior failure after review."""
        return self._fail(
            WorkflowState.BEHAVIOR_INCOMPATIBILITY,
            ResultClassification.BEHAVIOR_INCOMPATIBILITY,
            diagnostics or self.diagnostics,
        )

    def cancel(self) -> WorkflowSnapshot:
        self.state = WorkflowState.CANCELLED
        self.classification = None
        return self.snapshot()

    def cleanup(self) -> None:
        """Remove only the external baseline directory created by this workflow."""
        if self.baseline is None:
            return
        parent = self.baseline.parent.resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if (
            self.baseline.name == "behavior-baseline.json"
            and parent.name.startswith("retro-web-ui-baseline-")
            and parent.parent == temp_root
        ):
            shutil.rmtree(parent, ignore_errors=True)
        self.baseline = None

    def _refresh_analysis(self) -> WorkflowSnapshot:
        assert self.project_root is not None
        self.analysis = self.facade.analyze(self.project_root, self.selected_app)
        self.doctor = self.facade.doctor(self.project_root, self.selected_app)
        self.diagnostics = self.analysis.diagnostics + self.doctor.diagnostics
        selection = self.analysis.result["selection"]
        if selection.get("ambiguous"):
            self.state = WorkflowState.APP_SELECTION_REQUIRED
            self.classification = ResultClassification.REVIEW_REQUIRED
            self.approvals = []
        elif self.analysis.status == "ok" and self.doctor.status == "ok":
            self.state = WorkflowState.READY_FOR_BASELINE
            self.classification = None
            self._load_approvals()
        else:
            self._fail(WorkflowState.ERROR, ResultClassification.UNSUPPORTED, self.diagnostics)
        return self.snapshot()

    def _load_approvals(self) -> None:
        assert self.doctor is not None and self.project_root is not None
        selected = (self.doctor.result["selection"].get("selected") or {}).get("path") or "."
        app_root = self.facade.contained_path(self.project_root, selected, require_directory=True)
        pending: list[VerificationApproval] = []
        for identifier, plan in enumerate(self.doctor.result.get("verification_plan", [])):
            purpose = str(plan["purpose"])
            if not self._finite_verification_purpose(purpose):
                # dev/serve/watch commands are runtime hosts, not bounded
                # verification.  Starting one here would wait until timeout and
                # misclassify a successful conversion as failed.
                continue
            working_directory = self.facade.contained_path(app_root, plan.get("cwd", "."), require_directory=True)
            pending.append(VerificationApproval(
                identifier,
                purpose,
                working_directory,
                tuple(plan["argv"]),
                f"Run the target application's declared {purpose} verification command after conversion.",
                "This command is declared by the selected project. It may create build artifacts, run project hooks, or access local services; it is never executed by the CLI.",
            ))
        self.approvals = pending

    @staticmethod
    def _finite_verification_purpose(purpose: str) -> bool:
        normalized = purpose.strip().lower().replace("_", "-")
        return normalized in {
            "build", "test", "unit-test", "integration-test", "e2e-test",
            "lint", "typecheck", "type-check", "check", "verify",
        }

    def _fail(self, state: WorkflowState, classification: ResultClassification, diagnostics: list[dict[str, Any]]) -> WorkflowSnapshot:
        self.state = state
        self.classification = classification
        self.diagnostics = list(diagnostics)
        return self.snapshot()

    def _require_project(self) -> Path:
        if self.project_root is None:
            raise RuntimeError("Select a project first.")
        return self.project_root

    def _require_theme(self) -> str:
        if self.selected_theme is None:
            raise RuntimeError("Select a theme first.")
        return self.selected_theme

    def _require_baseline(self) -> Path:
        if self.baseline is None:
            raise RuntimeError("Create a behavior baseline first.")
        return self.baseline

    def _require_ready_for_baseline(self) -> None:
        if self.state != WorkflowState.READY_FOR_BASELINE:
            raise RuntimeError("Resolve application selection and environment diagnostics first.")
        self._require_theme()
