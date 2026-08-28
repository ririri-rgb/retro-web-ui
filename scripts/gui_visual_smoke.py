#!/usr/bin/env python3
"""Render a deterministic offscreen screenshot of the desktop shell."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from retro_web_ui_gui.widgets import ApprovalDialog, ApprovalRequest, MainWindow
from retro_web_ui_gui.xp_style import apply_xp_style


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "screenshots" / "gui" / "desktop-xp.png")
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "screenshots" / "gui")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    apply_xp_style(app)
    window = MainWindow()
    window.set_project("C:\\Projects\\sample-settings", [{"path": "apps/web"}, {"path": "apps/admin"}])
    window.set_analysis("Framework: React + Vite\nGit: clean\nApplication selection: apps/web\nBehavior baseline: ready")
    window.set_models([{
        "id": "gpt-5.6-terra",
        "displayName": "GPT-5.6-Terra",
        "isDefault": True,
        "defaultReasoningEffort": "medium",
        "supportedReasoningEfforts": [{"reasoningEffort": "low"}, {"reasoningEffort": "medium"}],
    }])
    window.set_codex_state("ready", "Codex is ready. Your existing ChatGPT sign-in will be used; no API key is requested.")
    window.add_agent_event({"kind": "analysis", "message": "Frontend application detected: apps/web"})
    window.add_agent_event({"kind": "baseline", "message": "Behavior baseline created outside the project"})
    window.add_agent_event({"kind": "agent", "message": "Semantic conversion completed; review verification and diff"})
    window.set_verification(
        "Build: passed\nBehavior: unchanged\nStatic audit: clean\nRuntime review: no console errors",
        result="complete",
    )
    window.set_diff("M apps/web/src/App.tsx\nM apps/web/src/styles.css\n?? apps/web/src/retro-windows-xp.css")
    window.set_before_after(
        ROOT / "screenshots" / "gui" / "static-before-modern.png",
        ROOT / "screenshots" / "gui" / "static-after-windows-xp.png",
    )
    window.show()
    app.processEvents()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    if not window.grab().save(str(args.output), "PNG"):
        raise SystemExit(f"failed to save screenshot: {args.output}")
    captures = [args.output.resolve()]

    window.review_tabs.setCurrentIndex(2)
    app.processEvents()
    verification_output = args.evidence_dir / "desktop-verification-complete.png"
    if not window.grab().save(str(verification_output), "PNG"):
        raise SystemExit(f"failed to save screenshot: {verification_output}")
    captures.append(verification_output.resolve())

    window.review_tabs.setCurrentIndex(4)
    app.processEvents()
    before_after_output = args.evidence_dir / "desktop-before-after.png"
    if not window.grab().save(str(before_after_output), "PNG"):
        raise SystemExit(f"failed to save screenshot: {before_after_output}")
    captures.append(before_after_output.resolve())

    approval = ApprovalDialog(ApprovalRequest(
        command="npm run build",
        cwd="C:\\Projects\\sample-settings\\apps\\web",
        reason="Verify the production build after semantic conversion.",
        risk="Runs a project-defined script. Review package.json before allowing it.",
    ), window)
    approval.show()
    app.processEvents()
    approval_output = args.evidence_dir / "desktop-approval-default-deny.png"
    if not approval.grab().save(str(approval_output), "PNG"):
        raise SystemExit(f"failed to save screenshot: {approval_output}")
    captures.append(approval_output.resolve())

    print("\n".join(str(path) for path in captures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
