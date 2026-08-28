"""A restrained Windows XP utility-window stylesheet for Qt Widgets.

This is an application shell, not a copy of proprietary Windows artwork.  The
controls intentionally remain native Qt controls so keyboard navigation and
assistive-technology metadata are retained.
"""

from __future__ import annotations


XP_STYLESHEET = """
QWidget {
    background: #ece9d8;
    color: #1c1c1c;
    font-family: "Tahoma", "Arial";
    font-size: 12px;
}
QMainWindow { background: #ece9d8; }
QMenuBar { background: #ece9d8; border-bottom: 1px solid #aca899; padding: 1px; }
QMenuBar::item { padding: 3px 8px; background: transparent; }
QMenuBar::item:selected { background: #316ac5; color: white; }
QMenu { background: #f7f5ec; border: 1px solid #7f9db9; }
QMenu::item { padding: 4px 24px 4px 18px; }
QMenu::item:selected { background: #316ac5; color: white; }
QToolBar { background: #ece9d8; border-bottom: 1px solid #aca899; spacing: 2px; padding: 2px; }
QToolButton { border: 1px solid transparent; padding: 3px 7px; min-height: 18px; }
QToolButton:hover { border-color: #316ac5; background: #c1d2ee; }
QToolButton:pressed, QToolButton:checked { border-color: #003c74; background: #98b9e7; }
QGroupBox { border: 1px solid #7f9db9; margin-top: 9px; padding: 8px 7px 7px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
QTabWidget::pane { border: 1px solid #7f9db9; top: -1px; }
QTabBar::tab { background: #d8e4f6; border: 1px solid #7f9db9; border-bottom: none; padding: 4px 10px; margin-right: 1px; }
QTabBar::tab:selected { background: #ece9d8; }
QTabBar::tab:focus { outline: 1px dotted #000000; }
QPushButton { min-height: 22px; padding: 2px 12px; background: #ece9d8; border: 1px solid #003c74; border-radius: 2px; }
QPushButton:hover { background: #f8f7f2; }
QPushButton:pressed { background: #c1d2ee; padding-top: 3px; padding-left: 13px; }
QPushButton:default { border: 2px solid #003c74; }
QPushButton:disabled { color: #838383; border-color: #aca899; background: #e3e1d6; }
QLineEdit, QPlainTextEdit, QComboBox, QListWidget, QTreeWidget {
    background: white; border: 1px solid #7f9db9; selection-background-color: #316ac5; selection-color: white;
}
QLineEdit, QComboBox { min-height: 20px; padding-left: 3px; }
QComboBox::drop-down { width: 19px; border-left: 1px solid #7f9db9; }
QHeaderView::section { background: #ece9d8; border: 1px solid #aca899; padding: 3px; font-weight: bold; }
QStatusBar { background: #ece9d8; border-top: 1px solid #aca899; }
QStatusBar::item { border: 1px solid #aca899; }
QProgressBar { border: 1px solid #7f9db9; text-align: center; background: white; height: 16px; }
QProgressBar::chunk { background: #316ac5; }
QLabel[role="error"] { color: #9b0000; font-weight: bold; }
QLabel[role="notice"] { color: #003c74; }
QWidget:focus { outline: 1px dotted #000000; }
"""


def apply_xp_style(application: object) -> None:
    """Apply the shell style without requiring callers to know Qt types."""
    application.setStyleSheet(XP_STYLESHEET)
