# Compatibility evidence

Evidence date: 2026-08-27. This is the bounded compatibility evidence adopted for `v1.0.0`.

The post-v1 CLI candidate reuses this semantic/runtime evidence rather than expanding it. Its additional deterministic evidence is recorded in [CLI + Skill validation report](cli-validation-report.md): six local fixtures exercised manifest/baseline/verify flow, the pinned TodoMVC repository exercised real monorepo app selection and unchanged behavior comparison, and package-manager support remains separated into runtime, historical, or synthetic levels.

Evidence levels used below are cumulative only when explicitly listed: **Detection**, **Build**, **Runtime**, **Behavior**, **Visual**, **Semantic conversion**, and **Real OSS**. A dependency being detected is never treated as runtime support.

| Target | Rendering / styling / architecture | Evidence reached | Verified boundary |
| --- | --- | --- | --- |
| Static HTML + Vanilla JS | browser DOM; plain CSS; native controls | Detection, Behavior, Runtime, Visual, Semantic conversion | hashed pre/post signals, click/form/tab keyboard smoke, modern plus four theme renders; strongest generic fallback evidence |
| TodoMVC Vanilla ES6 real OSS | client rendering; dependency CSS; hash routes | Build, Behavior, Runtime, Visual, Semantic conversion, Real OSS | pinned `tastejs/todomvc@ff43b02e...`; generated JS byte-identical, active/completed route state preserved, Windows 98 screenshot; upstream add/toggle baseline defect remained before conversion |
| React 19 + Vite 8 | client rendering; Tailwind detected; controlled state | Build, Behavior, Runtime, Visual, Semantic conversion | Japanese freeware conversion, unchanged state/handler signals, real click changed `aria-pressed`, label, and live status; small fixture, not broad React proof |
| React 19 + MUI 9 + Emotion | client rendering; CSS-in-JS; controlled input; portal dialog | Detection, Build, Runtime, Behavior, Visual, Semantic conversion | Windows 98 component overrides, controlled value, dialog portal, Escape, focus return, final DOM attributes and computed radius; one fixture and selected MUI controls only |
| Vue 3 + Vite 8 + Bootstrap 5 | client rendering; SFC/scoped CSS; actual Bootstrap JS modal; `v-model` | Detection, Build, Runtime, Behavior, Visual, Semantic conversion | Windows XP settings UI, native validation, submit/live status, Bootstrap shown/hidden events, utility-specificity adapter and computed style |
| SvelteKit 2 + Svelte 5 | adapter-static prerender followed by hydration; global theme import; `bind:*` | Detection, Build, Runtime, Behavior, Visual, Semantic conversion | Japanese freeware backup settings, controlled values/check, form/live status, hydrated production output; request-time SvelteKit SSR not tested |
| Next 16 App Router + Tailwind 4 + Radix Dialog | request-time SSR; stable server theme root; client island/hydration; portal; utility CSS | Detection, Build, Runtime, Behavior, Visual, Semantic conversion | Windows 7 settings, initial server HTML, hydration without mismatch, controlled form/live status, Escape/focus return, portal scope, Tailwind collision adapter, desktop/dialog/narrow captures |
| naive-ui-admin real OSS authentication surface | Vue 3/Vite; Naive UI; Pinia/router; scoped Less; async routes; partial-surface portal scope | Detection, Build, Runtime, Behavior, Visual, Semantic conversion, Real OSS (manual record) | pinned MIT checkout; demo login routed to dashboard, no console errors, body theme removed after route, Japanese freeware desktop/narrow inspection; dashboard itself not converted and the record is not rerun in CI |
| Four theme bundles | same showcase DOM/JS; CSS-only theme primitives | Build, Runtime, Visual | deterministic generation, unique structural selectors/tokens, interaction smoke and all-theme render; not evidence for every target CSS stack |

## Coverage by validation axis

- Framework/runtime: static/vanilla, React, Vue, SvelteKit, and Next.js have runtime semantic-conversion evidence.
- Rendering models: client rendering, static prerender plus hydration, request-time SSR plus hydration, route-driven UI, and client islands are exercised.
- Styling: plain CSS, global/scoped CSS, Tailwind utilities, Bootstrap utilities/plugins, and Emotion CSS-in-JS are exercised. Sass/CSS Modules are detected but do not yet have equivalent runtime semantic-conversion evidence.
- Components: native controls, controlled inputs, Bootstrap modal, MUI dialog portal, Radix dialog portal, and Naive UI form controls are exercised.
- Application classes: showcase/settings, authentication, backup utility, Todo, and settings/dialog surfaces are represented. Virtualized/table-heavy and visualization-heavy screens remain weak.
- Real OSS: TodoMVC and the naive-ui-admin authentication surface are pinned, licensed, non-vendored cases with separate evidence records. The naive-ui-admin conversion is explicitly a dated manual record rather than a CI fixture.
- CLI/package managers: npm is exercised by current fixtures and TodoMVC; pnpm has the dated naive-ui-admin record plus metadata tests; yarn and Bun have deterministic detection/argv tests only. None of those latter tests is presented as package-manager runtime proof.

## Failure-driven evidence

The browser smoke suite originally found `.retro-stack { display: grid }` overriding a tab panel's `hidden` attribute. The shared kit now preserves `[hidden]`, and all four themes plus interactions are regression-tested.

TodoMVC showed that a namespaced bundle alone can leave a modern application structure and dependency-owned fixed dimensions. A semantic conversion and narrow targeted adapter were required even though the static audit was clean.

Bootstrap showed that later source order does not beat an upstream `!important` utility. The fixture uses the narrowest theme-scoped adapter and validates the computed style. MUI 9 showed that deprecated passthrough props can land DOM/test attributes on the wrong slot, so the fixture uses current `slotProps` and checks the final DOM. Naive UI showed that a global body theme can leak from a partially converted route; portal-host theme mirroring is now lifecycle-scoped and route-cleanup is verified.

Detailed real-OSS records:

- [TodoMVC](real-oss-todomvc.md)
- [naive-ui-admin authentication surface](real-oss-naive-ui-admin.md)

## Conditional / best-effort

- Nuxt, Angular, Astro, CSS Modules, Sass, styled-components, complex uncontrolled custom selects, virtualized data grids, and chart-heavy dashboards have detection or written integration guidance but not the same runtime semantic-conversion evidence.
- Other versions and components of Bootstrap, MUI, Radix/shadcn, and Naive UI can differ in DOM, slots, CSS specificity, and portal behavior. Use the target's own runtime tests and computed-style inspection.
- Full-application conversion of a large mixed-style repository remains an iterative, surface-by-surface task; evidence for one route must not be generalized to untouched routes.
- SSR/meta-framework conversions must preserve the target's server/client boundary and verify initial HTML plus hydration. Next request-time SSR is exercised; Nuxt SSR and SvelteKit request-time SSR are not.

## Safely unsupported

Closed Shadow DOM, canvas/WebGL-only rendering, cross-origin iframe contents, binary/generated bundles without source, and native desktop applications cannot be reliably transformed without expanding beyond this Skill's safe source-editing model. Cross-origin or production-only authentication flows also cannot be exercised without user-provided authorization and a safe test environment.
