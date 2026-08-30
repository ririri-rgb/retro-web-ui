# Phase C GUI workspace validation report

Evidence closed: 2026-08-31 JST.

## 1. Baseline

- Public release: `v2.0.1`.
- Public tag commit: `5d56fc9` (`docs: finalize v2.0.1 release metadata`).
- Candidate branch: `codex/retro-web-ui-desktop-gui`.
- Inspected working baseline: `775903578a91a0e92828d729b733de122e2d0ad3`, one documentation commit after the public tag and equal to `origin/main` at inspection time.
- Validated source candidate: `dd34ee81dda96322e40de4e3d2fe2355ebda8a7d`.
- Fresh CI: [run 33340040216](https://github.com/ririri-rgb/retro-web-ui/actions/runs/33340040216).
- Fresh native artifacts: [run 33340045460](https://github.com/ririri-rgb/retro-web-ui/actions/runs/33340045460).

The published `v2.0.1` archives are immutable and do not contain this workspace.

No version, tag, release, `main` merge, or published artifact was created or
changed. All candidate-level claims below refer to the exact source commit
above; earlier failed/intermediate runs are retained only as failure-driven
history and are not counted as final evidence.

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
| Windows junction could evade a POSIX-style symlink test | persistence/security | `Path.is_symlink()` does not cover every Windows reparse point | Treat `FILE_ATTRIBUTE_REPARSE_POINT` as link-like at workspace, app, and artifact boundaries | synthetic reparse-attribute regression plus real `mklink /J` replacement at root/projects/project/session/artifacts on Windows Server 2025 |
| Interrupt transport failure left uncertain remote work and a locked GUI | controller/App Server | Cancel delegated directly to a failing bridge call | Mark transport lost, disable new start, unlock presentation, and require explicit status recovery | interrupt-transport regression |
| Directory `fsync` could report failure after a successful replace | persistence/portability | Some Windows/mounted filesystems do not support directory fsync | Keep file fsync/replace mandatory; make only directory fsync best effort | unsupported-directory-fsync regression |
| Initialized Workspace root could be replaced with a link and redirect later writes | persistence/security | Only leaf project/session/artifact paths were rechecked | Pin root/projects directory identity and revalidate both before every storage traversal | real macOS symlink escape reproduction followed by outside-write rejection regression; real Windows junction replay passed |
| A final `project.json` or `session.json` link could be followed | persistence/security | Record JSON used an unbounded path-level text read | Use bounded regular-file descriptor reads and reject the final link/reparse object | external session-record symlink regression |
| Basic/Digest authorization, login URLs, and device codes could survive inside allowed prose | privacy | Redaction covered bearer/JWT/query/cookie/private-key shapes but not all labeled credentials | Centralize free-text redaction for authorization headers, labeled secrets, login URLs, device/user codes, and credential URLs | expanded persisted-JSON privacy regression plus native lifecycle privacy scan |
| Browser/App Server smokes initially failed under the wrong host boundary | validation environment | Local Chrome and App Server were invoked in a restricted context | Re-run with the installed absolute Chrome and authorized local App Server boundary | structured App Server smoke and Chrome CDP passes |
| First fresh Windows GUI job failed before its junction gate | test isolation | The lifecycle test cleared all environment variables and mocked only `sys.platform`, creating a contradictory Windows `os.name`/Linux platform state with no home directory | Inject a temporary lifecycle workspace root directly; keep platform-root selection in its pure cross-platform tests | local full suite and second fresh Windows GUI suite passed the lifecycle test |
| Second fresh Windows junction job failed before creating a junction | integration-test portability | NTFS temporary paths used equivalent short (`RUNNER~1`) and long (`runneradmin`) spellings, while the test derived an escape suffix with lexical `Path.relative_to()` | Derive the expected suffix from the logical workspace schema and make junction-creation failure a hard failure rather than a skip | final Windows job created real junctions and passed all five boundary replacements |
| TodoMVC build was initially unavailable | real target environment | Pinned checkout had no dependencies | Bounded isolated npm cache/install in the disposable checkout | webpack build pass in 1.5 s |
| Todo creation still did not fire | upstream real target | Pinned app binds creation to a `change` path not triggered by Enter/blur automation | Preserve and report the pre-existing baseline limitation; do not call it a conversion pass | current browser replay plus prior pinned baseline record |

Schema `v1` is the first workspace format. A newer or unknown/older schema is
isolated and surfaced as an issue; no guessed migration exists yet because
there is no released older workspace schema to migrate.

## 6. Validation scale

- Full local Python discovery on the final source candidate: 148 tests, 140
  passes and eight intentional Qt/Windows skips in the CLI-only macOS
  interpreter. The existing PySide6 6.11.2 environment ran the 89
  GUI/controller/workspace/bridge/workflow tests with zero skips and failures.
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
- Fresh CI matrix on the final source candidate: Linux, macOS, and Windows CLI
  portability; Linux, macOS, and Windows GUI portability; Python and GUI
  minimum-version jobs; repository validation. All nine jobs passed.
- Real Windows junction gate: Windows Server 2025 created NTFS junctions with
  `cmd /c mklink /J` and replaced each of the initialized root, projects,
  project, session, and artifacts directories. Every write and integrity read
  failed closed; no outside write was accepted. Junction creation cannot skip.
- Chrome/CI browser: showcase + React production interaction passed; MUI/Emotion,
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

A separate final-candidate recovery probe checkpointed a real Terra-medium thread
and turn, terminated the local Codex App Server process, created a fresh
transport, resumed and read the same durable thread, verified its server cwd,
and classified the returned `interrupted` turn as
`interrupted_recoverable`. It reported candidate commit
`dd34ee81dda96322e40de4e3d2fe2355ebda8a7d`, candidate clean, binding verified,
fresh transport, and a clean workspace privacy scan. This is real local App
Server evidence, separate from the deterministic native lifecycle probe.

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
  their record directories. Windows reparse coverage includes both synthetic
  attribute tests and the fresh real-junction CI gate described above.
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

## 10. Cross-platform and artifact evidence

| Environment | Evidence class | Fresh final-candidate result |
| --- | --- | --- |
| macOS arm64 local host | native/offscreen plus real local App Server and installed Chrome | local 148-test discovery, PySide6 suite, candidate native build, browser/framework interaction, and real process-loss recovery passed |
| GitHub macOS arm64 | hosted runner, native executable, offscreen display | extracted archive started; Core/manifest/Skill/App Server/window checks passed; workspace `running` -> restart -> `transport_lost`, history 1/1, artifact integrity and privacy clean |
| GitHub Linux x86_64 | hosted runner, native executable, offscreen display | same lifecycle/startup checks passed; Linux ABI floor recorded as glibc 2.35, GLIBCXX 3.4.29, CXXABI 1.3.13 |
| GitHub Windows x86_64 | hosted runner, native executable, offscreen display | same lifecycle/startup checks passed; separate real NTFS junction containment gate passed at all five storage boundaries |
| Unit/static | synthetic | path-root decisions, reparse attributes, permissions branches, traversal, record links, corrupt/new schema, retention, privacy, and recovery state regressions passed |

All three downloaded final-candidate native reports recorded exact commit
`dd34ee81dda96322e40de4e3d2fe2355ebda8a7d` and `candidateClean: true`.
Sidecar SHA-256 files matched the downloaded archives:

- Linux x86_64: `a97d086fd785f69d4233a424f5b8e999824ff47ed619881ebc5f00303e3ffc5d`.
- macOS arm64: `5431e04b4cf2d6472699612dec26ff93e58629fe7d2ce1d429932a2b0a544019`.
- Windows x86_64: `505d2784cc020bfdcce852a86d34c41fa07c0a85f54db69b79b9ec0dc772e45a`.

Independent archive inspection validated all payloads and found zero absolute
or parent-traversal names and zero symlink entries (165 Linux, 166 macOS, and
91 Windows entries). Each extracted program reported version 2.0.1, Codex
external/not bundled, App Server ready, Core okay, manifest compatible, Skill
available, and a visible offscreen window. The deterministic lifecycle used
the platform-appropriate isolated workspace location, restored one project and
one session, preserved the artifact SHA
`28676b83b17fb426082c08c636b17187a7e952836d6c41402e8cb29662438854`,
and reported privacy clean.

No fresh user-owned physical Windows or Linux workstation test was performed.
The hosted runners are labeled hosted/native/offscreen, not physical-machine
evidence. Published `v2.0.1` evidence is not counted toward this candidate.

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
- Packaging: final-candidate native archives are CI artifacts, not published
  release assets. macOS is ad-hoc signed but not Developer ID signed/notarized;
  Windows is unsigned. No user-owned physical Windows/Linux install was run.
- Authentication: hosted native probes use an isolated home and intentionally
  report `sign_in_required`; they validate App Server availability, not a real
  signed-in account. Real signed-in recovery evidence is the separate local
  App Server probe.

## 12. Saturation evidence

Independent architecture, security/privacy, GUI, persistence, recovery, and
cross-platform reviews found failures in separate owning layers. The loop
reproduced and corrected root-anchor replacement, final-record following,
credential/device-code persistence, Windows lifecycle-test isolation, and NTFS
short/long path handling. Each correction gained a regression or integration
gate and was followed by a fresh candidate run.

Saturation for release **review** was reached when the exact source candidate
passed the full three-OS matrix, the real Windows junction gate, all three
native archive/startup/restart/privacy probes, downloaded-archive integrity and
traversal inspection, local full/PySide suites, browser/framework evidence,
and real App Server process-loss recovery without another P0/P1 cross-cutting
failure. This is not a claim of universal platform completeness or a release
authorization. Physical user-owned Windows/Linux, production signing, and
notarization remain release-process evidence, not silently inferred passes.

## 13. Release recommendation

**Ready for v2.1.0 release review.**

The change is additive but introduces a substantial user-visible workspace and
the first versioned persistence schema. The fresh evidence found no remaining
P0/P1 cross-cutting failure and no Core/CLI/Skill regression. The recommended
minor version remains `v2.1.0`; this report does not authorize changing the
version, creating a tag/Release, merging to `main`, or publishing artifacts.
Release review must explicitly accept or schedule production signing/notarization
and any desired user-owned physical Windows/Linux acceptance run.
