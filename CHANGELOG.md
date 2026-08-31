# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses semantic versioning.

## [Unreleased]

## [2.1.1] - 2026-08-31

### Changed

- Added a protected, manually approved pre-tag preflight that authoritatively verifies GitHub immutable-release enablement, unused tag and Release identity, and the exact default-branch commit before tag creation.
- Hardened tag-triggered publication to resolve and bind the exact successful preflight run, create one draft Release by immutable ID, upload only the manifest-bound asset set, and independently verify every public byte before certification.
- Pinned third-party GitHub Actions by commit and required Sigstore/DSSE provenance to bind the exact release tag and every expected asset digest.

### Security

- Release publication now fails closed on missing Administration-read credentials, mutable or malformed GitHub state, tag or Release collisions, provenance mismatches, unexpected assets, and any final `immutable` value other than the JSON boolean `true`.

## [2.1.0] - 2026-08-31

### Added

- Local Project/Conversion Session workspace with canonical project registration, independent UUID session lifecycles, restart reconciliation, historical inspection, integrity-aware comparison, and explicit Codex thread recovery.
- Versioned, atomically replaced workspace records and bounded evidence manifests for behavior baselines, deterministic Core results, agent assessment, and metadata-only Git observations.

### Changed

- The desktop controller now derives conversion/recovery controls from workflow and remote-turn state, locks project/history mutation during active work, and labels restored evidence as historical rather than current source truth.
- GUI portability CI now exercises the persistence and recovery regression suite alongside controller, bridge, workflow, and widget tests.

### Fixed

- Rejected stale cross-thread approval, user-input, diff, and completion events before they can affect the active conversion.
- Prevented raw Git patches, authentication-shaped values, symlinked workspace paths, malformed record IDs, and oversized post-capture artifact replacements from crossing persistence boundaries.
- Preserved the external behavior baseline durably before temporary cleanup and retained model/reasoning metadata across artifact updates.
- Degraded safely to conversion-without-history when the platform workspace directory cannot be initialized.

## [2.0.0] - 2026-08-29

### Added

- Windows XP-style PySide6 desktop application for project/application selection, four-theme selection, deterministic analysis, behavior baselines, agent progress, approvals, verification, Git diff, and Before/After review.
- A protocol-isolated `CodexBridge` using the local Codex App Server over stdio with the user's existing ChatGPT sign-in, model discovery, durable threads, streaming events, approvals, interruption, reconnect, and secret redaction.
- Host-native macOS, Windows, and Linux packages built and startup-tested in CI, with bundled Python/Qt runtimes, external Codex discovery, component inventories, license notices, and SHA-256 files.
- Fake-stream, state-machine, App Server contract, filesystem-scope, native archive, three-OS portability, accessibility, and GUI visual regression coverage.

### Changed

- Promoted the project from a CLI + Skill release to an end-to-end desktop orchestration product while keeping Core/CLI/Skill as the canonical deterministic and semantic boundaries.
- Native release publication now requires all three operating-system builds and the full existing CLI/Core/Skill/browser regression suite before GitHub Release creation.

### Fixed

- Restricted agent writes to the canonical selected application and rejected symlink/outside-root selection without reverting pre-existing user changes.
- Distinguished finite verification commands from long-running development servers and exposed review-required outcomes instead of treating static success as semantic proof.
- Made the installed/frozen GUI invoke the canonical bundled CLI/Core rather than relying on a source-checkout script path.
- Recovered App Server sessions through a fresh transport plus durable thread resume after an unexpected process exit.
- Declared Linux desktop runtime requirements and forced optional Qt modules into frozen bundles so native offscreen startup passes on all three CI hosts.

## [1.1.0] - 2026-08-27

### Added

- Installable `retro-web-ui` Python CLI with versioned JSON output for project analysis, environment diagnostics, behavior snapshots/comparison, theme assets, static audit, and read-only verification aggregation.
- Machine-readable Skill manifest covering CLI API compatibility, behavior signal contracts, and deterministic theme bundle digests.
- Monorepo-aware frontend candidate selection that requires an explicit `--app` when several applications are plausible.

### Changed

- Promoted the established v1.0 deterministic helpers into a shared Python package consumed by both the CLI and the Codex Skill while retaining the legacy script entry points.
- Reserved semantic conversion, application-specific repair, target-command selection, and visual judgment for the Skill instead of introducing an unsafe universal converter.

## [1.0.0] - 2026-08-27

### Added

- Runtime semantic-conversion fixtures for React/MUI/Emotion, Vue/Bootstrap, SvelteKit hydration, and Next request-time SSR with Radix/Tailwind.
- Dependency-free external Chrome DevTools Protocol interactions that independently exercise forms, modal/dialog lifecycle, Escape, focus return, and browser console/runtime errors.
- Rendering-model and component-architecture evidence in project inspection, including portals, route-driven UI, async loading, and virtualization markers.
- Pinned real-OSS naive-ui-admin authentication-surface evidence and theme-isolation guidance for partial-route conversions.

### Changed

- Expanded the behavior guard to cover multiline framework syntax, state setters/aliases, History API routes, timers/subscriptions, ARIA contracts, and test selectors; older signal baselines are intentionally rejected by the v4 algorithm.
- CI now uploads current browser renders for manual visual review in addition to interaction assertions.

### Fixed

- Prevented Bootstrap `!important` utilities from retaining modern pill/color styles through a narrowly scoped adapter.
- Used current MUI slot APIs so native input and dialog attributes reach the correct DOM nodes.
- Documented and regression-tested lifecycle-scoped portal-host theming so a partial conversion does not leak into the next route.

## [0.1.0] - 2026-08-27

### Added

- First public release of the `retro-web-ui` Codex Skill.
- Four structurally distinct, namespaced CSS themes.
- Framework/style detection and verification-command discovery.
- Hashed behavior baseline and comparison guard.
- Modern-style residue audit.
- Static, React, Vue, SvelteKit, Next.js, Tailwind, Bootstrap, and Radix-style detection fixtures.
- Dependency-free Python unit tests plus Chrome/Chromium showcase and React production interaction smoke tests.
- Pinned TodoMVC semantic conversion evidence with behavior, generated-JavaScript, route, and visual verification.
- Before/After screenshots, compatibility evidence, research, licensing, and contributor documentation.

### Fixed

- Ignored the SvelteKit fixture's static `build/` output so post-build CI and release cleanliness checks remain reproducible.
- Replaced pre-publication installation wording with a version-pinned GitHub Skill URL.
