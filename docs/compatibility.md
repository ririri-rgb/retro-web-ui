# Compatibility evidence

Evidence date: 2026-08-26.

| Target | Fixture/evidence | Checks passed | Boundary |
| --- | --- | --- | --- |
| Static HTML + Vanilla JS | `tests/fixtures/static-html`, browser showcase | detection, hashed behavior signals, CSS-only comparison, click/form/tab keyboard smoke, five renders | strongest current evidence |
| TodoMVC Vanilla ES6 real OSS | `tastejs/todomvc@ff43b02e59dfa604386bb382034b2cd07c2bcd8a` | semantic Windows 98 conversion, original/themed build, identical JS bundle, behavior compare unchanged, active/completed route state, Chrome screenshot | add/toggle baseline failed before theming; external source is not vendored |
| React 19 + Vite 8 + Tailwind 4 | `tests/fixtures/react-vite` | semantic Japanese freeware conversion, locked production build, unchanged state/handler signals, real Chrome click/status transition, screenshot | fixture is intentionally small; Tailwind dependency is detection evidence and not used by the rendered control |
| Vue 3 + Vite 8 + Bootstrap 5 | `tests/fixtures/vue-vite` and Bootstrap binding fixture | locked production build, model/form signals, `data-bs-*` risk | plugin runtime unverified |
| SvelteKit 2 + Svelte 5 | `tests/fixtures/svelte-kit` | locked static-adapter build, extension, binding and command detection | SSR/hydration beyond prerender unverified |
| Next 16 App Router + Tailwind 4 + Radix-style | `tests/fixtures/next-tailwind` | locked static build, styling/provider, form-contract detection | portals/server boundaries unverified |
| Four theme bundles | same showcase DOM/JS | deterministic generation, unique structural selectors/tokens, Chrome render | not evidence for every target CSS stack |

The browser smoke test found a real shared-CSS regression: `.retro-stack { display: grid }` overrode a tab panel's `hidden` attribute. The common kit was corrected to preserve `[hidden]`, then every theme and the interaction test were rerun. This is retained as a regression assertion.

Real OSS validation results are appended only after a pinned commit, license, commands, and observed result are recorded. Compatibility is not inferred merely from a dependency name.

Detailed TodoMVC evidence is in [real-oss-todomvc.md](real-oss-todomvc.md). A namespaced bundle alone changed an input edge but left the 80 px heading, Helvetica, shadow, and application structure modern. The subsequent semantic conversion passed build, behavior-signal, generated-JavaScript, route, and visual checks. Its first screenshot still exposed a dependency-owned fixed input height, which was corrected with a scoped adapter and rerun. This validates the Skill's requirement for semantic markup changes, computed-style inspection, and failure-driven iteration; `audit_ui.py: clean` is never treated as visual success.

## Conditional support

- React, Vue, and Svelte family applications with source templates are expected to work through scoped integration and context-aware edits, subject to target-native tests.
- Tailwind, Bootstrap, MUI, Vuetify, Radix/shadcn, and CSS-in-JS require provider/layer/specificity handling.
- SSR/meta-frameworks require stable root attributes and hydration checks.
- Monorepos must be analyzed per workspace.

## Safely unsupported

Closed Shadow DOM, canvas/WebGL-only rendering, cross-origin iframes, binary/generated bundles without source, and native desktop applications cannot be reliably transformed without expanding beyond this Skill's safe source-editing model.
