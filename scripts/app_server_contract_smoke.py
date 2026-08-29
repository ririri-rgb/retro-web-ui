#!/usr/bin/env python3
"""Exercise the live Codex App Server contract without modifying a target.

The smoke uses the current user's Codex login, sends the same stable
thread/turn fields as the GUI, denies any unexpected approval, and never logs
credentials or account identifiers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retro_web_ui_gui.codex_bridge import BridgeEvent, CodexBridge
from retro_web_ui_gui.controller import AGENT_RESULT_SCHEMA
from retro_web_ui_gui import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args(argv)

    terminal = threading.Event()
    observed: dict[str, Any] = {"approvals": 0, "terminalStatus": None, "structuredResult": None}
    bridge = CodexBridge(
        client_name="retro_web_ui_app_server_smoke",
        client_title="Retro Web UI App Server Contract Smoke",
        client_version=__version__,
    )

    def receive(event: BridgeEvent) -> None:
        if event.kind == "approval_requested":
            observed["approvals"] += 1
            approval = event.data.get("approval", {})
            if isinstance(approval, Mapping) and approval.get("requestId") is not None:
                bridge.deny(approval["requestId"])
        if event.kind == "user_input_requested":
            request_id = event.data.get("requestId")
            if request_id is not None:
                bridge.answer_user_input(request_id, {})
        if event.kind == "item_completed":
            params = event.data.get("params", {})
            item = params.get("item", {}) if isinstance(params, Mapping) else {}
            if isinstance(item, Mapping) and item.get("type") == "agentMessage" and item.get("phase") == "final_answer":
                try:
                    value = json.loads(str(item.get("text") or ""))
                except json.JSONDecodeError:
                    value = None
                if isinstance(value, Mapping):
                    observed["structuredResult"] = dict(value)
        if event.kind == "turn_completed":
            params = event.data.get("params", {})
            turn = params.get("turn", {}) if isinstance(params, Mapping) else {}
            observed["terminalStatus"] = turn.get("status") if isinstance(turn, Mapping) else None
            terminal.set()
        if event.kind == "unexpected_exit":
            observed["terminalStatus"] = "app_server_exited"
            terminal.set()

    remove_listener = bridge.add_listener(receive)
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="retro-web-ui-app-server-smoke-") as directory:
            root = Path(directory).resolve()
            bridge.start(cwd=root)
            account = bridge.account_read()
            account_value = account.get("account") if isinstance(account, Mapping) else None
            account_type = str(account_value.get("type") or "").lower() if isinstance(account_value, Mapping) else ""
            if account_type != "chatgpt":
                raise RuntimeError("Live smoke requires an existing ChatGPT Codex sign-in.")
            bridge.read_configuration(cwd=root)
            model_result = bridge.list_models()
            values = model_result.get("data", []) if isinstance(model_result, Mapping) else []
            advertised = {str(item.get("id") or item.get("model")) for item in values if isinstance(item, Mapping)}
            if args.model not in advertised:
                raise RuntimeError(f"Requested model is not advertised: {args.model}")
            thread_result = bridge.start_thread(cwd=str(root))
            thread = thread_result.get("thread", {}) if isinstance(thread_result, Mapping) else {}
            thread_id = str(thread.get("id") or "") if isinstance(thread, Mapping) else ""
            if not thread_id:
                raise RuntimeError("App Server did not return a thread ID.")
            bridge.start_turn(
                thread_id,
                [{"type": "text", "text": (
                    "Protocol smoke only. Do not edit files or run commands. Return classification complete, "
                    "summary READY, and empty changedFiles, reviewItems, verificationPerformed, and verificationUnavailable."
                )}],
                cwd=str(root),
                approvalPolicy="on-request",
                sandboxPolicy={"type": "workspaceWrite", "writableRoots": [str(root)], "networkAccess": False},
                model=args.model,
                effort=args.effort,
                outputSchema=AGENT_RESULT_SCHEMA,
            )
            if not terminal.wait(args.timeout):
                bridge.interrupt_turn(thread_id)
                raise TimeoutError("Timed out waiting for a terminal turn event.")
            bridge.read_thread(thread_id, include_turns=True)
            structured = observed["structuredResult"]
            structured_ok = bool(
                isinstance(structured, Mapping)
                and structured.get("classification") == "complete"
                and structured.get("summary") == "READY"
                and all(structured.get(key) == [] for key in (
                    "changedFiles", "reviewItems", "verificationPerformed", "verificationUnavailable"
                ))
            )
            result = {
                "status": "ok" if observed["terminalStatus"] in {"completed", None} and structured_ok else "error",
                "model": args.model,
                "terminalStatus": observed["terminalStatus"],
                "structuredOutput": "valid" if structured_ok else "invalid_or_missing",
                "approvalRequests": observed["approvals"],
                "elapsedSeconds": round(time.monotonic() - started, 3),
            }
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "ok" else 1
    finally:
        remove_listener()
        bridge.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
