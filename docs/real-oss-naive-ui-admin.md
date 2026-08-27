# Real OSS evidence: naive-ui-admin authentication surface

Evidence date: 2026-08-27

Evidence type: one-time manual validation record against the pinned commit. It is intentionally not a CI fixture: the 2.5 GB temporary checkout, dependency store, and build outputs were removed after evidence capture, and the upstream source/large transformation diff are not vendored.

## Target

- Repository: [`jekip/naive-ui-admin`](https://github.com/jekip/naive-ui-admin)
- Pinned commit: `3a469f1aca0b1b9d47d7c9e771c26dce058ea345`
- License: MIT, verified from the pinned checkout
- Source handling: shallow-cloned into a temporary directory and removed after validation; no upstream source is vendored here
- Architecture observed: Vue 3, Vite, Naive UI, Pinia, Vue Router, scoped Less, Tailwind dependency, async-loaded routes, controlled bindings, and virtualized-component markers

This target was selected because it combines a real component library, runtime-injected styles, authentication/routing, a large modern login composition, and an unconverted dashboard behind the converted surface. Only the authentication surface was semantically converted. The dashboard was used as a route/theme-leak regression target, not claimed as converted.

## Conversion

The modern glass/card login was recomposed as a compact Japanese freeware 2000s utility window with a menu row, account group box, conventional labels, standard command button, and status segments. The original language, Naive UI controls, `v-model` bindings, validation rules, submit handler, Pinia login action, redirect, demo credentials, checkbox, and secondary actions were retained.

The generated theme bundle was imported globally, while the permanent `data-retro-theme` root stayed on the login surface. Because Naive UI overlays may render outside that local root, the body attribute was mirrored only for the component lifetime and removed on unmount.

![naive-ui-admin login converted to Japanese Freeware 2000s](../screenshots/real-oss-naive-ui-admin-japanese-freeware.png)

## Checks performed

- Original production build: passed with pnpm 9.15 and a temporary project-local store.
- Converted production build: passed (6,251 transformed modules).
- Behavior baseline/compare: handler, Pinia, request, and routing signals stayed present. The guard required review for one changed form-contract signal and added form/accessibility/auth signals introduced by explicit labels and the reconstructed form surface.
- Real browser interaction: the original demo login command completed and routed to `/dashboard/console`.
- Route state: the dashboard heading and route were present after login; browser console errors were empty.
- Theme isolation: after routing away, `document.body.getAttribute("data-retro-theme")` was `null` and the unconverted dashboard was not left under the retro theme.
- Visual inspection: normal and 520 px wide captures were checked for clipping, control readability, density, and modern rounded-card residue.

The behavior guard result was not relabeled as unchanged. It remained `review-required`; the source diff and actual login/route behavior supplied the necessary review evidence.

## Failures and generalized outcomes

| Failure category | Observed failure | Generalized outcome |
| --- | --- | --- |
| Tooling/environment | A newer pnpm policy changed workspace metadata and skipped build scripts. | Preserve the pinned package-manager generation and use a temporary local cache/store; do not mutate system permissions. |
| Component-library/style | Naive UI owns runtime styles and overlay placement outside local markup. | Prefer current provider/slot APIs, inspect final DOM/computed styles, and explicitly account for the portal host. |
| Portal/theme scope | A body-level theme made the converted login look correct but leaked into the unconverted dashboard. | Whole-app and partial-surface theme roots now have separate guidance; temporary portal-host mirroring must be removed on teardown and route-tested. |
| Static audit boundary | Untouched dashboard files still contained modern patterns after a valid single-surface conversion. | Scope the claim and audit review to the intended conversion surface; do not report a whole application as converted. |

## Boundary

This manual record validates one real Vue/Naive UI authentication surface and its transition into an unconverted route at the evidence date. It is not a continuously reproduced CI guarantee and does not establish complete semantic conversion of naive-ui-admin, all Naive UI widgets, virtualized data tables, or every Vue application. The upstream warnings about Vite's CJS API, Browserslist age, and `eval` in `mockjs` were present independently of the theme conversion and were not altered.
