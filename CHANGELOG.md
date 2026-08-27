# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses semantic versioning.

## [Unreleased]

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
