# Desktop GUI architecture

This document describes the unreleased desktop GUI candidate. The published
`v1.1.0` release and its tags remain an immutable CLI + Skill baseline.

## Decision

The desktop application uses **PySide6 with Qt Widgets** and a restrained
Windows XP utility visual language. Qt Widgets provides the menu, property
tabs, group boxes, list views, dialogs, status bar, focus behavior, keyboard
navigation, and platform accessibility integration needed by this workflow.
It also lets the application reuse the Python Core and bundled CLI without
reimplementing them in Rust, TypeScript, or a local web service.

Tauri 2 was the runner-up because of its small OS-WebView distribution and
strong CSS fidelity. It was not selected because it would add a Rust-to-Python
sidecar boundary around the existing canonical Python implementation. Electron
was rejected because bundling Chromium adds material size and memory cost while
the repository already has an external Chrome/CDP validation harness.

Windows XP was selected over Windows 98 for the application shell. Its property
dialogs, tabs, wizard-like progression, progress UI, and command hierarchy fit
the dense conversion workflow. The application does not reproduce historical
accessibility defects or proprietary Microsoft assets.

## Boundaries

```text
Qt Widgets
  -> WorkflowController (presentation state and result classification)
     -> CoreFacade (bundled CLI JSON contract)
        -> retro_web_ui.core and existing deterministic helpers
     -> CodexBridge (stable application-facing interface)
        -> codex app-server over stdio JSONL
           -> the user's existing Codex/ChatGPT login
              -> Retro Web UI Skill and target application
```

`CoreFacade` invokes the CLI script bundled in the same installation. This
retains app-selection, manifest, output-safety, behavior, theme, audit, and
verification contracts that are not all exposed by the small public Core
facade. It parses one versioned JSON envelope and never treats a clean static
result as semantic success. Target-native verification commands remain plans
until a user approves the exact argv and working directory.

`CodexBridge` is GUI-independent. It owns discovery, process lifecycle,
initialize/initialized negotiation, request correlation, account/config/model
discovery, thread/turn lifecycle, streaming events, approval responses,
tool user input, interrupt, diff accumulation, redaction, crash detection,
fresh-transport restart, durable-thread resume, and shutdown. The GUI
never parses raw App Server messages.

## App Server compatibility

The implementation follows the current official [Codex App Server
documentation](https://developers.openai.com/codex/app-server/). The primary
transport is the default local stdio JSONL child process. WebSocket is not used
for the desktop-local path. The Bridge obtains models at runtime and reuses the
account reported by `account/read`; it never requests or stores an OpenAI API
key.

Compatibility is gated by executable discovery, `codex --version`, successful
`initialize`, and required method behavior. A packaged schema snapshot is not
treated as authoritative because `codex app-server generate-json-schema`
produces a protocol bundle for the installed CLI. Optional/experimental fields
are only sent after capability negotiation.

The local research prototype used Codex CLI `0.150.0-alpha.8` and completed:

```text
initialize -> account/read -> model/list -> thread/start -> turn/start
           -> item/agentMessage/delta -> turn/completed -> stdio EOF
```

The first attempt sent `runtimeWorkspaceRoots` without negotiating
`experimentalApi` and received JSON-RPC error `-32600`. The generalized fix is
capability-aware request construction, not a version-specific exception.

## Safety model

- The selected project and application are canonicalized before a session.
- Symlinked roots and paths outside the selected root are rejected.
- Every turn uses an explicit workspace-write sandbox whose only writable root
  is the canonical selected application; network is disabled.
- Existing Git changes are reported and never reverted automatically.
- Behavior baselines live outside the target by default.
- Command, file-change, and additional-permission approvals display the raw
  operation, working directory, reason, network/filesystem scope, and risk
  before a decision is returned; Deny is the default.
- App Server stdout is protocol-only; stderr and diagnostic logs are redacted.
- Authentication tokens, device codes, account email, and auth URLs are not
  persisted by the application.
- Cancellation interrupts the active turn and waits for the interrupted terminal
  event before classifying the result.
- Conversion completion, deterministic verification, behavior compatibility,
  and visual review are separate states.

## Distribution direction

The GUI dependency is optional (`.[gui]`) so the CLI + Skill remain usable
without Qt. `pyside6-deploy` is the primary native packaging route for macOS,
Windows, and Linux. Wheel installation, GUI startup, and state/bridge tests are
defined per operating system in CI; signing, notarization, and updater configuration remain release-review work
because no production release is created in this engineering phase.

The implementation and failure-driven evidence are recorded in the [Desktop
GUI engineering report](gui-validation-report.md).
