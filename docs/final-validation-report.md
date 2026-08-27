# Final validation report: v1.0.0 release basis

Date: 2026-08-27

Baseline: immutable public `v0.1.0` at `6c8cc3ea70ab0a8f891fe9752a664452cfe3ba15`

Recommendation: **Approved as the evidence basis for v1.0.0**. Release-only versioning, clean validation, security, packaging, tag, and publication checks remain separate gates and do not expand the capability claims in this report.

## Summary

The project has moved from one strong React conversion plus static/TodoMVC evidence to a multi-framework runtime validation set covering component-library CSS, portals, static hydration, and request-time SSR. The largest improvements are behavior-guard v4, production runtime semantic conversions for MUI/Emotion, Bootstrap, SvelteKit, and Next/Radix/Tailwind, external browser interactions with console/runtime capture, and a second real-OSS application surface that exposed partial-route theme leakage.

The evidence supports a useful cross-framework Codex Skill, not a universal converter. Meaning-dependent structural changes still require Codex review and target-native tests.

## Validation scale

- 8 runtime or real-OSS application surfaces: static showcase, React/Vite, React/MUI, Vue/Bootstrap, SvelteKit, Next App Router, TodoMVC, and naive-ui-admin login.
- 2 pinned real-OSS repositories: TodoMVC and naive-ui-admin; neither is vendored.
- 5 framework/runtime families with semantic runtime evidence: static/vanilla, React, Vue, SvelteKit, and Next.js.
- Rendering: client rendering, static prerender + hydration, request-time SSR + hydration, route-driven UI, async-loaded UI observation, and server/client islands.
- Styling: plain/global CSS, scoped SFC CSS, Tailwind utilities, Bootstrap CSS/JS, Emotion CSS-in-JS, and Naive UI/scoped Less in a manual real-OSS record.
- 4 exercised component-library strategies: MUI, Bootstrap, Radix headless portal, and Naive UI.
- 4 themes rendered from one common showcase; all four also appear in semantic evidence across distinct application surfaces.
- 32 dependency-free Python unit/regression tests, 5 locked production builds, 2 browser harnesses, and 4 external CDP framework scenarios.

## Fully validated within explicit fixtures

- Static/vanilla four-theme rendering and keyboard/click behavior.
- React/Vite Japanese freeware controlled-state conversion.
- React/MUI/Emotion Windows 98 controlled form and portal dialog.
- Vue/Bootstrap Windows XP form and actual modal lifecycle.
- SvelteKit adapter-static Japanese freeware output followed by hydration and interaction.
- Next App Router Windows 7 request-time server HTML followed by client hydration, Tailwind collision handling, and Radix portal interaction.
- TodoMVC pinned real-OSS Windows 98 conversion, including byte-identical generated JS and hash-route state.

“Fully” here means the documented fixture/surface and assertions, not every component or version in the named ecosystem.

## Partially validated

- naive-ui-admin: its login/authentication surface, real route transition, and theme cleanup were manually validated; the dashboard and virtualized/table surfaces were not converted, and this heavy target is not rerun in CI.
- Sass and CSS Modules: detector coverage exists, but no equivalent runtime semantic conversion.
- Async-loaded and virtualized architectures: observed/detected in real or synthetic targets; their hardest runtime surfaces remain unconverted.

## Best effort and unsupported

- Nuxt SSR, Angular, Astro, styled-components, complex uncontrolled custom selects, virtualized data grids, chart/canvas-heavy dashboards, and full large-application conversions remain best-effort until target-specific evidence exists.
- Closed Shadow DOM, cross-origin iframe contents, canvas/WebGL-only UI, binary/generated UI without source, and native desktop applications are safely unsupported by this source-editing Skill.
- Production-only or cross-origin authentication cannot be exercised without authorized test credentials and a safe environment.

## Failures discovered and generalized

| Category | Failure | Generalized improvement |
| --- | --- | --- |
| Behavior guard false positive | imports/classes near an unchanged handler changed its hash | hash the normalized protected expression, not neighboring UI source |
| Behavior guard false negative | multiline/framework events, setters, History API, timers, ARIA, selectors were missed | v4 signal grammar plus adversarial regression cases and baseline-version rejection |
| Shared theme CSS | `display:grid` defeated native `hidden` | explicit themed `[hidden]` invariant and all-theme regression |
| CSS specificity | Bootstrap pill/color `!important` survived later CSS | narrow, theme-scoped upstream-selector adapter and computed-style assertion |
| Component slots | deprecated MUI props reached the wrong DOM wrapper | current `slotProps`, final-DOM contract checks |
| Transition timing | arbitrary sleeps raced Bootstrap modal state | await library lifecycle events |
| Portal scope | partial login conversion themed the next route through `body` | distinguish whole-app vs partial roots; lifecycle-scope portal-host mirroring and verify teardown |
| SSR/hydration evidence | DOM dump stderr did not prove browser console cleanliness | initial server HTML assertion plus Chrome logging and external CDP console/runtime capture |
| Test independence | app-embedded selftests were the only interaction driver | external normal-URL CDP form/dialog/Escape/focus flows added without a browser dependency |
| CI environment | Linux Chrome could still write into its profile after the parent process exited | wait for process termination and retry deletion of the exact temporary profile |
| Static/visual audit | clean heuristics missed dependency-owned dimensions and runtime CSS | computed-style and screenshot inspection remain mandatory |

## Behavior preservation

Behavior guard v4 materially expands syntax coverage and explicitly invalidates older baselines. The runtime set covers controlled inputs, checkboxes, forms, validation/trim, live regions, route transitions, hash routes, library modal events, portal scope, Escape, and focus return. TodoMVC retains an especially strong byte-identical generated-JavaScript case.

Remaining limit: hashes cannot prove equivalence, resolve arbitrary dynamic aliases, understand every handler body, or observe production-only runtime wiring. A `review-required` result is not suppressed merely because added signals appear beneficial.

## Visual validation

Current normal, narrow, and dialog images were generated from clean production builds and matched the reviewed repository images byte-for-byte. Manual inspection found and corrected hidden-panel, dependency-height, Bootstrap pill/color, portal radius/scope, and partial-route leakage issues. The four common themes remain structurally distinct.

CI now generates and uploads current renders. It does not use pixel thresholds; screenshots still require human fidelity review, which is appropriate because semantic quality and theme authenticity cannot be reduced safely to a golden-image score alone.

## Regression and repository quality

- Clean lockfile install passed with a repository-local cache.
- Five production builds passed.
- 32 unit/regression tests passed on Python 3.14 locally; CI retains Python 3.9 minimum and Python 3.12 validation jobs.
- Both Skill validators passed.
- Production npm audit: zero vulnerabilities. Three low findings remain only in the fixture development graph through SvelteKit's `cookie@0.6.0`.
- Static showcase/React interaction smoke, four-theme rendering, framework runtime selftests, external CDP interactions, initial SSR HTML, and console/runtime capture passed.
- Package license/archive tests and diff hygiene remain in CI/release gates.
- Two independently generated standalone Skill ZIPs were byte-identical, and validation after extraction passed.

## Security, license, storage

No Windows proprietary assets or upstream source trees were added. New JavaScript packages are locked test-fixture dependencies and production audit is clean. The second real-OSS screenshot carries its pinned source and MIT notice in `THIRD_PARTY_NOTICES.md`. Temporary real-OSS data (about 2.5 GB) and final render scratch directories were removed; no new system software was installed.

## Saturation evidence

The selected targets deliberately changed multiple axes at once: CSS-in-JS/deep library DOM, Bootstrap `!important` and lifecycle, Svelte prerender/hydration, Next request SSR/client island/portal/utility CSS, and a real Vue admin app with an authentication route boundary. They produced several new generalized failures early. After v4 behavior coverage, scoped adapters, lifecycle events, portal-root teardown, external CDP driving, and console capture were added, the heterogeneous regression set passed without another new cross-cutting failure.

The remaining gaps now cluster around known boundaries—virtualization, canvas/closed DOM, untested frameworks, production authentication, and application-specific full-surface work—rather than another unresolved failure shared by the currently exercised architectures. This is sufficient saturation for a v1 release review, while still leaving an honest roadmap.

## v1 release boundary

- v1.0.0 adopts the explicit validated, partial, best-effort, and unsupported boundaries above without adding another framework, component library, conversion algorithm, or application surface.
- Version/README/changelog alignment, clean package reproduction, final secret scan, tag, and GitHub Release are release gates rather than new capability evidence.
- Virtualized/table-heavy validation remains future work and is deliberately outside the v1.0.0 promise.
