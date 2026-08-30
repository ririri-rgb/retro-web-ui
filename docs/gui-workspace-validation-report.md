# Phase C GUI workspace validation report

Evidence date: 2026-08-30.

## 1. Baseline

- Public release: `v2.0.1`.
- Public tag commit: `5d56fc9` (`docs: finalize v2.0.1 release metadata`).
- Candidate branch: `codex/retro-web-ui-desktop-gui`.
- Inspected working baseline: `775903578a91a0e92828d729b733de122e2d0ad3`, one documentation commit after the public tag and equal to `origin/main` at inspection time.
- Candidate commit: not assigned at the time this report was written. The validated candidate is the reviewable working tree described here; no tag or release was created.

The published `v2.0.1` archives are immutable and do not contain this workspace.

This implementation report is now being extended by the Phase C
cross-platform release-validation loop. Candidate-level CI/native evidence is
not attributed until the working tree is committed and the exact SHA is run.

## 2. Architecture

`WorkspaceStore` is a standard-library, file-backed layer below the desktop
controller and outside `ConversionWorkflow`. It owns canonical Project records,
Conversion Session records, lifecycle transitions, evidence manifests,
integrity checks, limits, and atomic persistence. It does not own or copy the
selected repository.

Each project and session has a canonical UUID directory and a separate
schema-versioned JSON record. Artifacts are immutable session copies with
SHA-256 and byte length. The external behavior baseline, Core analysis/doctor,
verification, structured agent assessment, and metadata-only Git observations
can be retained. Raw App Server events, prompts, command output, Git patch
content, account payloads, login URLs, and credentials are excluded.

Historical views read only stored evidence and label it as historical. Current
project availability and artifact integrity are shown separately. A stored Git
observation contains HEAD, changed paths, stat, and patch digest/size; it is not
presented as an exclusive agent diff or proof of current source state.

`ConversionWorkflow` still owns one live conversion and deterministic result
classification. `CoreFacade` still owns canonical CLI/Core operations, source
containment, Git inspection, and approved target commands. `CodexBridge` still
owns App Server transport, authentication reuse, protocol correlation,
approvals, and redaction. `DesktopController` is the composition boundary that
checkpoints those layers into a session and maps verified state to the GUI.

## 3. Implemented user workflow

1. Select or reopen a canonical registered project.
2. Select exactly one application in a monorepo and one of four themes.
3. Create the external behavior baseline through the canonical Core/CLI.
4. Start a new Conversion Session. The baseline is copied and integrity-checked
   before the narrow temporary source is removed.
5. Create a Codex thread and turn bound to the selected application; persist
   thread/turn IDs as soon as each exists.
6. Stream only matching thread/turn events, request approvals, and lock project,
   model, theme, history inspection, comparison, and duplicate start controls.
7. Run explicitly approved finite target commands, canonical verification, and
   structured assessment; checkpoint a terminal or review classification.
8. After restart, inspect recorded sessions, compare artifact integrity, open an
   available project, or explicitly recover a lost thread for review.

Recovery never silently continues an interrupted turn. A matching remote active
turn remains `running`; a matching terminal turn becomes
`interrupted_recoverable`; missing/mismatched/unknown status fails closed.

## 4. Session state model

Meaningful persistent states are:

```text
draft -> prepared -> running <-> awaiting_approval
                         |
                         +-> verification_pending <-> verifying
                         |
                         +-> transport_lost -> running
                         |                  -> interrupted_recoverable
                         |
                         +-> interrupted_recoverable
                         +-> complete
                         +-> complete_with_review_items
                         +-> review_required
                         +-> behavior_incompatibility
                         +-> failed

terminal outcome -> archived
```

Invalid transitions raise an error. Startup converts only nonterminal active
states to `transport_lost`; recorded terminal outcomes remain terminal.

## 5. Failure-driven iterations

| Failure | Layer | Root cause | Generalized correction | Regression evidence |
| --- | --- | --- | --- | --- |
| Temporary baseline disappeared during session preparation | controller/persistence | One-shot workflow owned the only copy | Copy, hash, re-open, then remove only the known temporary source | completion/restart and close/recovery controller tests |
| Artifact capture erased model/reasoning metadata | persistence | Positional record reconstruction omitted later fields | Immutable `dataclasses.replace` updates | lifecycle metadata test |
| A dirty Git patch could persist source secrets | privacy | Full formatted diff was treated as ordinary bytes | Persist HEAD/path/stat plus patch size/hash only; never raw patch by default | secret-patch controller regression and real workspace scan |
| Tampered large artifact could consume unbounded memory | persistence | Integrity inspection used `read_bytes()` after capture | regular-file descriptor checks, size preflight, 64 KiB streaming, hard cap | oversized replacement regression |
| Malformed IDs and symlinked record directories could cross storage boundaries | persistence/security | Generic identifiers were interpolated as paths | canonical UUID record IDs, directory/record identity binding, symlink rejection at every workspace level | record-ID and symlink tests |
| Corrupt session directories evaded the session limit | retention | Limit counted only parseable sessions | Count all stored session directories, including unusable records | bounded-store implementation review |
| Stale App Server events could affect the active session | controller/protocol | Approval/input/diff paths lacked exact thread/turn filtering | Exact active thread and turn required; stale approvals denied and input dismissed | stale-event regression |
| Recovery enabled a retry without checking remote work | controller/App Server | `read_thread` result was informational only | Verify returned thread ID, optional cwd, and active/terminal/unknown status | active, terminal, mismatched, and unknown recovery tests |
| Reconnect could bypass the stricter recovery decision | controller/App Server | Reconnect read durable metadata but always returned to ready | Apply the same active/terminal/unknown and thread-ID checks before enabling controls | active and mismatched reconnect regression |
| Unexpected startup transport exit invented an interrupted conversion | controller | Exit handler unconditionally mutated workflow state | Interrupt only a real active project/thread and reset transport readiness | no-active-conversion exit test |
| Invalid duplicate start left an orphan draft | controller | Session creation preceded workflow-state validation | Validate allowable state before persistence | orphan-session regression |
| Session comparison could leave unrelated screenshots visible | presentation | Text changed but Before/After did not reset | Clear visual comparison when byte-level session comparison opens | controller comparison behavior |
| History selection could overwrite active review | presentation | Session list remained interactive while busy | Disable project/session history, comparison, and recovery during a live turn | native Qt busy-state regression |
| Read-only application-data directory prevented GUI startup | composition | Workspace initialization was mandatory | Start with `workspace=None` and a persistent diagnostic | native Qt degradation test |
| Windows junction could evade a POSIX-style symlink test | persistence/security | `Path.is_symlink()` does not cover every Windows reparse point | Treat `FILE_ATTRIBUTE_REPARSE_POINT` as link-like at workspace, app, and artifact boundaries | synthetic reparse-attribute regression; fresh Windows junction test remains a release gate |
| Interrupt transport failure left uncertain remote work and a locked GUI | controller/App Server | Cancel delegated directly to a failing bridge call | Mark transport lost, disable new start, unlock presentation, and require explicit status recovery | interrupt-transport regression |
| Directory `fsync` could report failure after a successful replace | persistence/portability | Some Windows/mounted filesystems do not support directory fsync | Keep file fsync/replace mandatory; make only directory fsync best effort | unsupported-directory-fsync regression |
| Initialized Workspace root could be replaced with a link and redirect later writes | persistence/security | Only leaf project/session/artifact paths were rechecked | Pin root/projects directory identity and revalidate both before every storage traversal | real macOS symlink escape reproduction followed by outside-write rejection regression; real Windows junction replay pending |
| A final `project.json` or `session.json` link could be followed | persistence/security | Record JSON used an unbounded path-level text read | Use bounded regular-file descriptor reads and reject the final link/reparse object | external session-record symlink regression |
| Basic/Digest authorization, login URLs, and device codes could survive inside allowed prose | privacy | Redaction covered bearer/JWT/query/cookie/private-key shapes but not all labeled credentials | Centralize free-text redaction for authorization headers, labeled secrets, login URLs, device/user codes, and credential URLs | expanded persisted-JSON privacy regression plus native lifecycle privacy scan |
| Browser/App Server smokes initially failed under the wrong host boundary | validation environment | Local Chrome and App Server were invoked in a restricted context | Re-run with the installed absolute Chrome and authorized local App Server boundary | structured App Server smoke and Chrome CDP passes |
| TodoMVC build was initially unavailable | real target environment | Pinned checkout had no dependencies | Bounded isolated npm cache/install in the disposable checkout | webpack build pass in 1.5 s |
| Todo creation still did not fire | upstream real target | Pinned app binds creation to a `change` path not triggered by Enter/blur automation | Preserve and report the pre-existing baseline limitation; do not call it a conversion pass | current browser replay plus prior pinned baseline record |

Schema `v1` is the first workspace format. A newer or unknown/older schema is
isolated and surfaced as an issue; no guessed migration exists yet because
there is no released older workspace schema to migrate.

## 6. Validation scale

- Full Python discovery: 148 tests discovered, with 140 passes and eight
  intentional Qt/Windows skips in the CLI-only macOS interpreter; after installing no new
  GUI dependency, the existing
  PySide6 6.11.2 environment ran the 89 GUI/controller/workspace/bridge/workflow
  tests with zero skips and zero failures.
- Workspace persistence tests: 24 plus one native-lifecycle smoke, covering canonical identity, lifecycle,
  restart, corruption, schema isolation, permissions, artifact bounds,
  traversal, tampering, comparison, and privacy.
- Controller tests: 26, including durable completion, close/restart, active and
  terminal recovery, unknown/mismatched thread state, stale events, duplicate
  start, and raw-patch exclusion.
- Native Qt widget tests: 7, including workspace signals, busy locking,
  accessibility names, bounded event history, and persistence degradation.
- Existing packaging, Core/CLI/Skill, theme, behavior guard, and archive tests
  remained in the 148-test discovery run.
- Chrome: showcase + React production interaction passed; MUI/Emotion,
  Vue/Bootstrap, SvelteKit, and Next/Radix external CDP interactions passed.
- Fixture builds: all five existing framework fixtures passed earlier in this
  candidate loop. Repository validator, npm production audit, CLI clean-install
  package smoke, and two-build byte reproducibility also passed.

The final counts must be read with their scope: unit and static passes do not
replace browser, native package, or physical-host evidence.

## 7. Real workflow

The meaningful real-project run used the MIT-licensed `tastejs/todomvc` commit
`ff43b02e59dfa604386bb382034b2cd07c2bcd8a`, selecting
`examples/javascript-es6` from its multi-application repository.

```text
Project registration
-> UUID session creation
-> real Codex App Server turn (gpt-5.6-terra, medium)
-> Windows XP semantic conversion
-> canonical verification
-> controller close/reopen
-> terminal session restoration
```

The turn took 230.676 s and changed four source paths. It finished
`complete_with_review_items`, correctly retaining missing build/browser work as
review items. Reopening the store restored the same classification, baseline
integrity was `available`, and startup reconciled zero terminal sessions.

Independent follow-up installed the locked dependency graph only in the
disposable target (450 packages), built successfully with webpack 5.89.0, and
confirmed the generated `app.bundle.js` SHA-256 remained
`01b56caf970328499b1ea12a405bd4c03e27bc4bad6d6e36d49884fe75159fac`.
Canonical `verify` returned `ok`, audit `clean`, and behavior `unchanged`;
`git diff --check` passed.

The in-app browser confirmed `data-retro-theme="windows-xp"`, `#/active` route
retention, zero captured console errors, a 30 px input, visible 2 px focus
outline, desktop computed width 526 px, and at 390 x 844 a 380 px window with no
horizontal overflow and wrapped status layout. Todo creation remained blocked
by the known upstream baseline event behavior and is not claimed as passed.

A separate working-tree recovery probe checkpointed a real Terra-medium thread
and turn, terminated the local Codex App Server process, created a fresh
transport, resumed and read the same durable thread, verified its server cwd,
and classified the returned `interrupted` turn as
`interrupted_recoverable`. The workspace privacy scan was clean. This proves
the recovery path locally, but it must be rerun after a candidate SHA is fixed
before it becomes candidate-level evidence.

## 8. Security and privacy

- ChatGPT authentication stays in Codex; the GUI stores no API key or token.
- Redaction covers sensitive keys, bearer/JWT/key-shaped values, authorization
  headers, labeled secrets, login/credential URLs, device/user codes, secret
  query parameters, cookie headers, and private-key blocks.
- No raw App Server stream, prompt, approval payload, command output, or Git
  patch is persisted. The real 840 KiB workspace passed a credential-pattern
  scan and contained no `.patch` artifact.
- Project/application paths are canonicalized; application and artifact
  containment rejects traversal, symlinks, and link-like Windows reparse
  points. Project/session path components are canonical UUIDs bound back to
  their record directories. Current Windows coverage for reparse points is
  synthetic; a real junction replay remains required before release.
- POSIX directories/files are best-effort `0700`/`0600`. Windows relies on the
  user's inherited application-data ACL; no stronger ACL claim is made.
- Codex writes remain limited to the exact selected application with network
  disabled. The workspace does not rollback or take ownership of source.

## 9. Storage and performance

Hard limits are 256 stored session directories per project, 64 artifacts per
session, 2,000,000 bytes per artifact, and 16,000 UTF-8 bytes per persisted text
field. Limits fail closed; nothing is silently deleted. GUI event history keeps
the newest 500 display entries and is not persisted.

The real TodoMVC session used 840 KiB across ten files, including the baseline
for a 4,495-file monorepo checkout. The real turn took 230.676 s. The later
webpack build took about 1.5 s; its isolated `node_modules` used about 63.6 MiB
and npm cache about 12.1 MiB. These are observations from one macOS arm64 run,
not general performance guarantees.

## 10. Cross-platform evidence

**Actual working-tree evidence (candidate SHA not yet assigned):** macOS 26.5.2 arm64, Python 3.12.13,
PySide6 6.11.2, Node 25.9.0, npm 11.12.1; native Qt offscreen rendering, real
Codex App Server conversion/restart, Chrome and in-app-browser interaction.

**CI-only design/evidence:** the workflow now includes `test_workspace` in the
existing GUI portability job and adds an Ubuntu/Python 3.9 GUI minimum job.
Windows x86_64 and Linux x86_64 paths, default
workspace locations, archive logic, and POSIX/Windows branches have unit/static
coverage, but this candidate has not yet produced a fresh three-OS CI run.

**Physical-machine evidence:** no new physical Windows or Linux run was
performed for Phase C. Published `v2.0.1` has earlier three-OS distribution
evidence, but it cannot be relabeled as validation of the new workspace.

## 11. Known limitations

- GUI: no session delete/export UI, no automatic screenshot capture, and
  comparison is integrity/equality metadata rather than visual ranking.
- History: raw patches are intentionally absent; current-source reconstruction
  and rollback are out of scope. A moved project is reported unavailable and is
  not guessed or silently rebound.
- Persistence: schema v1 has no legacy migration because no older workspace
  schema was released. Windows privacy uses inherited ACLs.
- App Server: recovery depends on durable thread readability. Server-side cwd
  binding is verified only when returned; otherwise the UI labels it unverified.
  Unknown status remains disabled rather than guessed resumable.
- Conversion: static/behavior success does not prove visual fidelity,
  accessibility, or every runtime flow. TodoMVC's pre-existing creation-event
  limitation remains.
- Packaging: no fresh signed/notarized native archive or physical Windows/Linux
  install was produced for this unversioned candidate.

## 12. Saturation evidence

Local cross-cutting convergence was reached for the persistence/controller/GUI
boundaries: independent architecture, security, GUI, persistence, and
cross-platform reviews
found failures in separate layers. The cross-platform continuation then found
and reproduced root-anchor replacement, final-record following, and free-text
credential persistence before candidate fixation; the corrections were
generalized and added
to restart, corruption, identity, stale-event, recovery, privacy, native Qt,
real App Server, real OSS, build, and browser regressions. Re-running the local
suite did not expose another failure, but the new containment correction still
requires its real Windows junction replay before its P0 disposition is closed.

Release saturation was **not** reached. A fresh candidate three-OS CI matrix,
native archives, and physical Windows/Linux workspace/recovery runs remain.
Therefore this report does not call Phase C universally complete or release
ready.

## 13. Release recommendation

Recommend `v2.1.0`: the change is additive but introduces a substantial
user-visible workspace and the first versioned persistence schema. It does not
break the CLI/Core/Skill contract and does not justify a major version.

Release readiness: **not yet**. Merge review plus a fresh green three-OS CI and
native archive/install validation should precede version bump, tag, or GitHub
Release. No release, tag, historical-tag change, or publication was performed.
