# Desktop GUI architecture

This document describes the v2 desktop GUI architecture. The published
`v1.1.0` release and its tags remain an immutable pre-GUI CLI + Skill baseline.

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
  -> DesktopController (composition and presentation state)
     -> WorkspaceStore (project/session identity and evidence references)
     -> ConversionWorkflow (one live conversion and result classification)
     -> CoreFacade (bundled CLI JSON contract)
        -> retro_web_ui.core and existing deterministic helpers
     -> CodexBridge (stable application-facing interface)
        -> codex app-server over stdio JSONL
           -> the user's existing Codex/ChatGPT login
              -> Retro Web UI Skill and target application
```

## Project and conversion-session workspace

The GUI owns a local, versioned file workspace under the platform application
data directory. This layer registers canonical project roots and gives each
conversion its own UUID, lifecycle, Codex thread/turn references, configuration,
and integrity-checked evidence manifest. It does not copy or own the selected
source repository.

Project records and session records are separate JSON documents so one corrupt
session does not hide unrelated history. Writes use a same-directory temporary
file, `fsync`, and atomic replacement. On supported POSIX hosts, directories are
mode `0700` and files are mode `0600`. Each project is limited to 256 sessions;
the application fails closed at the limit instead of silently deleting history.
Artifacts are limited to 2 MB each and 64 per session.

The artifact store copies the external behavior baseline and records bounded
Core evidence plus start/end Git observations. Every copied artifact has a byte
length and SHA-256 digest. History views report `available`, `missing`,
`changed`, `not captured`, or `not applicable` rather than silently regenerating
evidence. Git observations retain the HEAD fingerprint, changed paths, stat,
and a patch digest/size, but not raw patch content. They may include pre-existing
user work and are never presented as exclusive agent attribution.

The workspace persists no raw App Server event stream, prompt, account payload,
login URL, approval payload, command output, or authentication credential. A
stored Codex thread ID is a reference, not a resumable conversion guarantee.
Recovery is explicit, revalidates the exact local project/application and
baseline digest, requires the returned durable thread ID to match, and branches
on the remote turn status. A still-running turn remains locked and
interruptible; a confirmed terminal turn becomes review/retry eligible; an
unknown status fails closed. When App Server returns a working directory it
must match the selected application, while its absence is labeled as an
unverified server-side binding. Recovery never automatically resumes a turn.

Nonterminal `running`, `awaiting_approval`, `verifying`, and
`verification_pending` sessions become `transport_lost` after a process restart.
Terminal classifications remain terminal only when their recorded manifest says
so. Reopening a session never evaluates current source and labels it historical;
current project availability and artifact integrity are reported separately.

`CoreFacade` invokes the canonical CLI parser and handlers in-process from an
installed or frozen package, while a raw source checkout can still use the same
CLI through its subprocess boundary. This retains app-selection, manifest,
output-safety, behavior, theme, audit, and verification contracts without
duplicating algorithms. It parses one versioned JSON envelope and never treats
a clean static result as semantic success. Target-native verification commands
remain plans until a user approves the exact argv and working directory.

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

## Distribution

The GUI dependency is optional (`.[gui]`) so the CLI + Skill remain usable
without Qt. The recorded PySide deployment configuration and pinned Nuitka
compiler produce host-native macOS, Windows, and Linux packages in CI. Every
package runs GUI/Core/Skill/App Server readiness smoke before upload and ships
license texts plus a hashed component inventory. Codex is discovered externally
and is never bundled. macOS is ad-hoc signed but not notarized, Windows is
unsigned, Linux requires its documented desktop system libraries, and v2 has no
auto-updater.

The implementation and failure-driven evidence are recorded in the [Desktop
GUI engineering report](gui-validation-report.md).
