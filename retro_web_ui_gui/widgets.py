"""Accessible, compact Qt Widgets for the Retro Web UI desktop workflow.

All methods receive plain dictionaries/dataclasses or call injected objects by
capability.  This keeps presentation testable with fakes and prevents App
Server protocol details from leaking into UI controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


THEMES: tuple[tuple[str, str, str], ...] = (
    ("windows-98", "Windows 98", "Compact gray controls and classic dialog hierarchy."),
    ("windows-xp", "Windows XP", "Luna-inspired task and property-dialog appearance."),
    ("windows-7", "Windows 7", "Reserved glass-era desktop utility styling."),
    ("japanese-freeware-2000s", "Japanese Freeware 2000s", "Dense utility panels and Japanese desktop-software character."),
)

SCREENSHOTS = {
    "windows-98": "showcase-windows-98.png",
    "windows-xp": "showcase-windows-xp.png",
    "windows-7": "showcase-windows-7.png",
    "japanese-freeware-2000s": "showcase-japanese-freeware-2000s.png",
}


class WorkflowPort(Protocol):
    def select_project(self, root: str) -> None: ...
    def select_theme(self, theme_id: str) -> None: ...
    def start_conversion(self) -> None: ...
    def cancel(self) -> None: ...


@dataclass(frozen=True)
class AgentEvent:
    kind: str
    message: str
    detail: str = ""


@dataclass(frozen=True)
class ApprovalRequest:
    command: str
    cwd: str
    reason: str
    risk: str = "Review the command and its working directory before allowing it."


class ApprovalDialog(QDialog):
    """Explicit command approval; no vague "continue" decision is exposed."""

    def __init__(self, request: ApprovalRequest, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Codex requests permission")
        self.setModal(True)
        self.setMinimumWidth(510)
        self.setAccessibleName("Codex command approval")
        layout = QVBoxLayout(self)
        intro = QLabel("Codex needs permission before it can perform this operation.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for label, value in (("Command:", request.command), ("Working directory:", request.cwd), ("Reason:", request.reason), ("Risk:", request.risk)):
            text = QPlainTextEdit(value)
            text.setReadOnly(True)
            text.setMaximumHeight(52)
            text.setAccessibleName(label.rstrip(":"))
            form.addRow(label, text)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Cancel).setText("Deny")
        buttons.button(QDialogButtonBox.Ok).setText("Allow")
        buttons.button(QDialogButtonBox.Cancel).setDefault(True)
        buttons.button(QDialogButtonBox.Cancel).setFocus()
        buttons.button(QDialogButtonBox.Ok).setAutoDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class UserInputDialog(QDialog):
    """Render App Server tool questions without exposing protocol objects."""

    def __init__(self, request: Mapping[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Codex requests information")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._answers: dict[str, QComboBox] = {}
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Codex needs your answer before it can continue."))
        form = QFormLayout()
        for index, raw in enumerate(request.get("questions") or ()):  # type: ignore[union-attr]
            question = raw if isinstance(raw, Mapping) else {}
            question_id = str(question.get("id") or f"question_{index}")
            selector = QComboBox()
            selector.setEditable(True)
            for option in question.get("options") or ():
                if isinstance(option, Mapping):
                    selector.addItem(str(option.get("label") or option.get("description") or ""))
                else:
                    selector.addItem(str(option))
            selector.setAccessibleName(str(question.get("question") or question.get("header") or question_id))
            form.addRow(str(question.get("question") or question.get("header") or question_id) + ":", selector)
            self._answers[question_id] = selector
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Cancel).setText("Cancel turn input")
        buttons.button(QDialogButtonBox.Ok).setText("Send answers")
        buttons.button(QDialogButtonBox.Cancel).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def answers(self) -> Mapping[str, list[str]]:
        return {
            question_id: [selector.currentText().strip()]
            for question_id, selector in self._answers.items()
            if selector.currentText().strip()
        }


class MainWindow(QMainWindow):
    """Windows XP-like utility shell driven only by a small workflow port."""

    project_selected = Signal(str)
    application_selected = Signal(str)
    theme_selected = Signal(str)
    login_requested = Signal()
    reconnect_requested = Signal()
    conversion_requested = Signal()
    conversion_cancelled = Signal()
    approval_decided = Signal(bool)

    def __init__(self, workflow: WorkflowPort | None = None, *, asset_root: Path | None = None) -> None:
        super().__init__()
        self._workflow = workflow
        self._asset_root = asset_root or Path(__file__).resolve().parents[1]
        self._current_theme = "windows-xp"
        self._build_window()
        self._connect_port()
        self.set_codex_state("unavailable", "Codex availability has not been checked. Local project analysis remains available.")

    def _build_window(self) -> None:
        self.setWindowTitle("Retro Web UI GUI")
        self.setMinimumSize(900, 620)
        self.resize(1120, 760)
        self._build_menu()
        self._build_toolbar()
        self._build_status()
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(7, 5, 7, 5)
        self.readiness = QLabel()
        self.readiness.setWordWrap(True)
        self.readiness.setProperty("role", "notice")
        self.readiness.setAccessibleName("Codex readiness")
        root.addWidget(self.readiness)
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._build_setup_panel())
        splitter.addWidget(self._build_review_tabs())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.choose_action = QAction("&Select Project…", self, shortcut=QKeySequence.Open)
        self.choose_action.triggered.connect(self.choose_project)
        file_menu.addAction(self.choose_action)
        file_menu.addSeparator()
        quit_action = QAction("E&xit", self, shortcut=QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        session_menu = self.menuBar().addMenu("&Codex")
        self.login_action = QAction("Sign in with &ChatGPT…", self)
        self.login_action.triggered.connect(self.login_requested.emit)
        session_menu.addAction(self.login_action)
        self.reconnect_action = QAction("&Reconnect App Server", self)
        self.reconnect_action.triggered.connect(self.reconnect_requested.emit)
        self.reconnect_action.setEnabled(False)
        session_menu.addAction(self.reconnect_action)
        session_menu.addSeparator()
        self.start_action = QAction("&Start conversion", self, shortcut="Ctrl+Return")
        self.start_action.triggered.connect(self.request_conversion)
        session_menu.addAction(self.start_action)
        self.cancel_action = QAction("&Interrupt agent", self, shortcut="Esc")
        self.cancel_action.triggered.connect(self.cancel_conversion)
        self.cancel_action.setEnabled(False)
        session_menu.addAction(self.cancel_action)
        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("&About Retro Web UI GUI", self)
        about.triggered.connect(lambda: QMessageBox.about(self, "About", "Retro Web UI GUI\nA local Codex orchestration utility."))
        help_menu.addAction(about)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Workflow", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        self.stage_labels: dict[str, QLabel] = {}
        for index, (key, label) in enumerate((("project", "1 Project"), ("analysis", "2 Analyze"), ("theme", "3 Theme"), ("agent", "4 Codex"), ("verify", "5 Verify")), start=1):
            stage = QLabel(label)
            stage.setFrameStyle(QFrame.Panel | QFrame.Sunken)
            stage.setMargin(4)
            stage.setAccessibleName(f"Workflow stage {index}: {label}")
            toolbar.addWidget(stage)
            self.stage_labels[key] = stage
        toolbar.addSeparator()
        toolbar.addAction(self.start_action)

    def _build_status(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)
        self.status_message = QLabel("Ready")
        self.status_message.setAccessibleName("Application status")
        status.addWidget(self.status_message, 1)
        self.status_phase = QLabel("Offline")
        self.status_phase.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        status.addPermanentWidget(self.status_phase)

    def _build_setup_panel(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        project_box = QGroupBox("Project and application")
        project_layout = QGridLayout(project_box)
        self.project_path = QLineEdit()
        self.project_path.setPlaceholderText("Choose the project repository to analyze")
        self.project_path.setAccessibleName("Selected project path")
        self.project_path.setReadOnly(True)
        project_layout.addWidget(QLabel("Project root:"), 0, 0)
        project_layout.addWidget(self.project_path, 0, 1)
        self.browse_button = QPushButton("&Browse…")
        self.browse_button.setAccessibleName("Choose project directory")
        self.browse_button.clicked.connect(self.choose_project)
        project_layout.addWidget(self.browse_button, 0, 2)
        self.app_list = QListWidget()
        self.app_list.setAccessibleName("Detected frontend applications")
        self.app_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.app_list.itemSelectionChanged.connect(self._application_changed)
        project_layout.addWidget(QLabel("Application:"), 1, 0, Qt.AlignTop)
        project_layout.addWidget(self.app_list, 1, 1, 1, 2)
        layout.addWidget(project_box, 3)
        theme_box = QGroupBox("Conversion theme")
        theme_layout = QVBoxLayout(theme_box)
        self.theme_combo = QComboBox()
        self.theme_combo.setAccessibleName("Conversion theme")
        for theme_id, name, description in THEMES:
            self.theme_combo.addItem(name, (theme_id, description))
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        theme_layout.addWidget(self.theme_combo)
        self.theme_description = QLabel()
        self.theme_description.setWordWrap(True)
        self.theme_description.setAccessibleName("Theme description")
        theme_layout.addWidget(self.theme_description)
        self.preview = QLabel("Preview unavailable")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(230, 118)
        self.preview.setMaximumHeight(145)
        self.preview.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.preview.setAccessibleName("Selected theme visual preview")
        theme_layout.addWidget(self.preview, 1)
        layout.addWidget(theme_box, 2)
        codex_box = QGroupBox("Codex session")
        codex_layout = QFormLayout(codex_box)
        self.model_combo = QComboBox()
        self.model_combo.setAccessibleName("Codex model")
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        codex_layout.addRow("Model:", self.model_combo)
        self.effort_combo = QComboBox()
        self.effort_combo.setAccessibleName("Reasoning effort")
        codex_layout.addRow("Reasoning:", self.effort_combo)
        self.account_label = QLabel("Not connected")
        self.account_label.setWordWrap(True)
        self.account_label.setAccessibleName("Codex account status")
        codex_layout.addRow("Account:", self.account_label)
        self.login_button = QPushButton("Sign in with &ChatGPT…")
        self.login_button.clicked.connect(self.login_requested.emit)
        self.login_button.setEnabled(False)
        codex_layout.addRow("", self.login_button)
        layout.addWidget(codex_box, 2)
        # XP is the application shell's default and the combo must display the
        # same theme whose description/preview is shown.
        self.theme_combo.setCurrentIndex(1)
        return panel

    def _build_review_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        self.review_tabs = tabs
        tabs.setAccessibleName("Workflow evidence tabs")
        analysis = QWidget()
        analysis_layout = QVBoxLayout(analysis)
        self.analysis_text = QPlainTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setAccessibleName("Project analysis")
        self.analysis_text.setPlaceholderText("Select a project to see deterministic analysis and diagnostics.")
        analysis_layout.addWidget(self.analysis_text)
        tabs.addTab(analysis, "Analysis")
        agent = QWidget()
        agent_layout = QVBoxLayout(agent)
        self.event_list = QListWidget()
        self.event_list.setAccessibleName("Codex agent events")
        agent_layout.addWidget(self.event_list)
        tabs.addTab(agent, "Codex activity")
        verification = QWidget()
        verification_layout = QVBoxLayout(verification)
        self.result_banner = QLabel("No conversion result yet")
        self.result_banner.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.result_banner.setMargin(6)
        self.result_banner.setAccessibleName("Conversion result classification")
        verification_layout.addWidget(self.result_banner)
        self.verification_text = QPlainTextEdit()
        self.verification_text.setReadOnly(True)
        self.verification_text.setAccessibleName("Verification result")
        verification_layout.addWidget(self.verification_text)
        tabs.addTab(verification, "Verification")
        diff = QWidget()
        diff_layout = QVBoxLayout(diff)
        self.diff_text = QPlainTextEdit()
        self.diff_text.setReadOnly(True)
        self.diff_text.setAccessibleName("Modified files and diff review")
        diff_layout.addWidget(self.diff_text)
        tabs.addTab(diff, "Diff review")
        before_after = QWidget()
        pair = QHBoxLayout(before_after)
        self.before_preview = self._image_panel("Before")
        self.after_preview = self._image_panel("After")
        pair.addWidget(self.before_preview)
        pair.addWidget(QLabel("→", alignment=Qt.AlignCenter))
        pair.addWidget(self.after_preview)
        tabs.addTab(before_after, "Before / After")
        return tabs

    @staticmethod
    def _image_panel(title: str) -> QLabel:
        panel = QLabel(f"{title}\nNo screenshot available")
        panel.setAlignment(Qt.AlignCenter)
        panel.setMinimumSize(260, 180)
        panel.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        panel.setAccessibleName(f"{title} screenshot")
        return panel

    def _connect_port(self) -> None:
        if self._workflow is None:
            return
        self.project_selected.connect(self._workflow.select_project)
        self.theme_selected.connect(self._workflow.select_theme)
        self.conversion_requested.connect(self._workflow.start_conversion)
        self.conversion_cancelled.connect(self._workflow.cancel)

    def choose_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select project repository")
        if directory:
            self.set_project(directory)
            self.project_selected.emit(directory)

    def set_project(self, root: str, applications: list[Mapping[str, Any]] | None = None) -> None:
        self.project_path.setText(root)
        self.app_list.clear()
        for app in applications or []:
            path = str(app.get("path") or app.get("root") or app.get("name") or "Unknown application")
            item = QListWidgetItem(path)
            item.setData(Qt.UserRole, dict(app))
            self.app_list.addItem(item)
        if self.app_list.count() == 1:
            self.app_list.setCurrentRow(0)
        self._set_stage("project")
        self.status_message.setText("Project selected. Run analysis to inspect its application structure.")

    def set_analysis(self, result: str) -> None:
        self.analysis_text.setPlainText(result)
        self._set_stage("analysis")

    def set_codex_state(self, state: str, message: str) -> None:
        labels = {
            "ready": "Codex ready",
            "auth_required": "Sign in required",
            "unavailable": "Codex unavailable",
            "running": "Codex running",
            "interrupted": "Agent interrupted",
            "error": "Codex error",
        }
        self.readiness.setText(message)
        self.status_phase.setText(labels.get(state, state.replace("_", " ").title()))
        self.start_action.setEnabled(state == "ready")
        self.cancel_action.setEnabled(state == "running")
        self.login_action.setEnabled(state == "auth_required")
        self.login_button.setEnabled(state == "auth_required")
        self.reconnect_action.setEnabled(state == "error")
        self._set_stage("agent" if state == "running" else "project")

    def set_models(self, models: list[Mapping[str, Any]], *, account_text: str = "Signed in with ChatGPT") -> None:
        """Populate only models advertised by the installed Codex runtime."""
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        default_index = 0
        for index, model in enumerate(models):
            identifier = str(model.get("id") or model.get("model") or "")
            if not identifier:
                continue
            label = str(model.get("displayName") or identifier)
            efforts = model.get("supportedReasoningEfforts") or []
            normalized_efforts = [
                str(item.get("reasoningEffort")) if isinstance(item, Mapping) else str(item)
                for item in efforts
            ]
            data = {
                "id": identifier,
                "efforts": normalized_efforts,
                "defaultEffort": str(model.get("defaultReasoningEffort") or "medium"),
            }
            self.model_combo.addItem(label, data)
            if model.get("isDefault"):
                default_index = self.model_combo.count() - 1
        self.model_combo.setCurrentIndex(default_index if self.model_combo.count() else -1)
        self.model_combo.blockSignals(False)
        self.account_label.setText(account_text)
        self._model_changed(self.model_combo.currentIndex())

    def open_external_url(self, url: str) -> bool:
        """Open an App Server supplied sign-in URL without retaining it."""
        return QDesktopServices.openUrl(QUrl(url))

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        self.project_path.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)
        self.choose_action.setEnabled(not busy)
        self.reconnect_action.setEnabled(not busy and self.status_phase.text() == "Codex error")
        self.app_list.setEnabled(not busy)
        self.theme_combo.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self.effort_combo.setEnabled(not busy)
        self.start_action.setEnabled(not busy and self.status_phase.text() == "Codex ready")
        if message:
            self.status_message.setText(message)

    def selected_model(self) -> str | None:
        data = self.model_combo.currentData()
        return str(data.get("id")) if isinstance(data, Mapping) and data.get("id") else None

    def selected_effort(self) -> str | None:
        return str(self.effort_combo.currentData() or self.effort_combo.currentText()) or None

    def add_agent_event(self, event: AgentEvent | Mapping[str, Any]) -> None:
        if isinstance(event, Mapping):
            event = AgentEvent(str(event.get("kind", "event")), str(event.get("message", "")), str(event.get("detail", "")))
        item = QListWidgetItem(f"[{event.kind}] {event.message}")
        item.setToolTip(event.detail or event.message)
        self.event_list.addItem(item)
        self.event_list.scrollToBottom()

    def request_approval(self, request: ApprovalRequest | Mapping[str, str]) -> bool:
        if isinstance(request, Mapping):
            request = ApprovalRequest(**{key: str(request.get(key, "")) for key in ("command", "cwd", "reason", "risk")})
        dialog = ApprovalDialog(request, self)
        allowed = dialog.exec() == QDialog.Accepted
        self.approval_decided.emit(allowed)
        self.add_agent_event(AgentEvent("approval", "Command allowed" if allowed else "Command denied", request.command))
        return allowed

    def request_user_input(self, request: Mapping[str, Any]) -> Mapping[str, list[str]]:
        dialog = UserInputDialog(request, self)
        if dialog.exec() != QDialog.Accepted:
            self.add_agent_event(AgentEvent("user_input", "Codex input request cancelled"))
            return {}
        answers = dialog.answers()
        self.add_agent_event(AgentEvent("user_input", "Codex input answers sent"))
        return answers

    def set_verification(self, text: str, *, result: str = "Review required") -> None:
        self.verification_text.setPlainText(text)
        labels = {
            "complete": "Complete",
            "complete_with_review_items": "Complete with review items",
            "review_required": "Review required",
            "verification_failed": "Verification failed",
            "behavior_incompatibility": "Behavior incompatibility",
            "agent_interrupted": "Agent interrupted",
            "authentication_required": "Authentication required",
            "unsupported": "Unsupported / manual intervention required",
            "unsupported_manual_intervention_required": "Unsupported / manual intervention required",
        }
        label = labels.get(result, result.replace("_", " ").title())
        self.result_banner.setText(label)
        color = "#d6f0d2" if result == "complete" else "#fff2bf" if "review" in result else "#ffd6d6"
        self.result_banner.setStyleSheet(f"background: {color}; font-weight: bold;")
        self.status_message.setText(result)
        self._set_stage("verify")

    def set_diff(self, text: str) -> None:
        self.diff_text.setPlainText(text)

    def set_before_after(self, before: str | Path | None, after: str | Path | None) -> None:
        self._set_image(self.before_preview, before, "Before")
        self._set_image(self.after_preview, after, "After")

    def _set_image(self, label: QLabel, path: str | Path | None, title: str) -> None:
        pixmap = QPixmap(str(path)) if path else QPixmap()
        if pixmap.isNull():
            label.setPixmap(QPixmap())
            label.setText(f"{title}\nNo screenshot available")
            return
        label.setText("")
        label.setPixmap(pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _theme_changed(self, index: int) -> None:
        if index < 0:
            return
        theme_id, description = self.theme_combo.itemData(index)
        self._current_theme = theme_id
        self.theme_description.setText(description)
        screenshot = self._asset_root / "screenshots" / SCREENSHOTS[theme_id]
        if screenshot.is_file():
            self._set_image(self.preview, screenshot, "Theme preview")
        else:
            self.preview.setText("")
            self.preview.setPixmap(self._generated_theme_preview(theme_id).scaled(
                self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        self.theme_selected.emit(theme_id)
        self._set_stage("theme")

    @staticmethod
    def _generated_theme_preview(theme_id: str) -> QPixmap:
        """Small code-native fallback for installed wheels without screenshots."""
        colors = {
            "windows-98": ("#008080", "#000080", "#c0c0c0"),
            "windows-xp": ("#5a7edc", "#0755d5", "#ece9d8"),
            "windows-7": ("#7db0d3", "#4f83ad", "#f0f5f8"),
            "japanese-freeware-2000s": ("#d7d4c8", "#2357a6", "#f3f0df"),
        }
        workspace, title, face = colors.get(theme_id, colors["windows-xp"])
        pixmap = QPixmap(250, 125)
        pixmap.fill(QColor(workspace))
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor("#202020"), 1))
        painter.setBrush(QColor(face))
        painter.drawRect(24, 15, 201, 94)
        painter.setBrush(QColor(title))
        painter.drawRect(25, 16, 199, 18)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(31, 29, "Retro Web UI")
        painter.setPen(QColor("#777777"))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(40, 48, 168, 18)
        painter.setBrush(QColor(face))
        painter.drawRect(143, 78, 65, 19)
        painter.end()
        return pixmap

    def _application_changed(self) -> None:
        item = self.app_list.currentItem()
        if item is None:
            return
        data = item.data(Qt.UserRole)
        if isinstance(data, Mapping):
            selected = data.get("path") or data.get("root") or data.get("name")
        else:
            selected = item.text()
        if selected:
            self.application_selected.emit(str(selected))

    def _model_changed(self, index: int) -> None:
        self.effort_combo.clear()
        if index < 0:
            return
        data = self.model_combo.itemData(index)
        if not isinstance(data, Mapping):
            return
        efforts = list(data.get("efforts") or ["medium"])
        default = str(data.get("defaultEffort") or "medium")
        for effort in efforts:
            label = str(effort)
            self.effort_combo.addItem(label.capitalize(), label)
        selected = self.effort_combo.findData(default)
        self.effort_combo.setCurrentIndex(selected if selected >= 0 else 0)

    def request_conversion(self) -> None:
        if not self.project_path.text():
            QMessageBox.warning(self, "Project required", "Select a project before starting a conversion.")
            return
        self.conversion_requested.emit()
        self.set_codex_state("running", "Codex is planning and applying the semantic conversion. Review approvals before allowing commands.")

    def cancel_conversion(self) -> None:
        self.conversion_cancelled.emit()
        self.set_codex_state("interrupted", "The agent was interrupted. Existing edits were preserved for diff review.")

    def _set_stage(self, active: str) -> None:
        order = ("project", "analysis", "theme", "agent", "verify")
        for key in order:
            label = self.stage_labels[key]
            if key == active:
                label.setStyleSheet("background: #316ac5; color: white; font-weight: bold;")
            else:
                label.setStyleSheet("background: #ece9d8; color: #1c1c1c;")
