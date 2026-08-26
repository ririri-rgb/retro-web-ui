# Real OSS evidence: TodoMVC Vanilla ES6

Evidence date: 2026-08-26.

- Repository: [tastejs/todomvc](https://github.com/tastejs/todomvc)
- Target: `examples/javascript-es6`
- Commit: `ff43b02e59dfa604386bb382034b2cd07c2bcd8a` (2026-05-02)
- License: MIT
- Validation environment: isolated shallow/sparse checkout and dedicated Python virtual environment

## Passed

- `inspect_project.py`: static/Vanilla, npm, build/dev commands, source inventory.
- Original build, bundle-only integration build, and semantic Windows 98 conversion build: webpack compiled successfully.
- Generated `app.bundle.js` was byte-identical before/after (`01b56caf970328499b1ea12a405bd4c03e27bc4bad6d6e36d49884fe75159fac`).
- Revised behavior baseline comparison: `unchanged`, with zero protected-signal changes.
- Existing different bundle output was refused; `--check` accepted the current bundle.
- Semantic conversion changed markup, wrappers, classes, and CSS while leaving controller, model, store, template, route targets, and generated JavaScript unchanged.
- Browser route filters `#/active` and `#/completed` retained their hash and selected state.
- Real Chrome inspection confirmed the compact title/menu/group-box/status composition and removal of the 80 px heading, modern card shadow, Helvetica typography, and oversized field.
- The visual result is retained as [`screenshots/todomvc-windows-98.png`](../screenshots/todomvc-windows-98.png); the upstream source tree is not vendored.

## Baseline failure

Todo creation could not be triggered in the original checkout using Enter, incremental typing, or blur-equivalent browser actions. The source binds creation to a `change` event. Completion/toggle flow was therefore unreachable. The current Store uses in-module memory rather than `localStorage`, so persistence could not be validated. This existed before theming and is recorded as an upstream/environment baseline failure, not a passed behavior check.

## Failure-driven feedback

Adding the bundle and theme root without semantic markup edits was not a successful Windows 98 conversion. The 550 px modern card, 80 px red heading, Helvetica body, large shadow, and TodoMVC structure remained. Only the input minimum height/edge visibly changed. Modern styles came from an npm dependency excluded by the source audit.

This failure produced three general improvements:

1. Behavior hashes no longer include preceding import/layout context, eliminating a CSS-import false positive.
2. The hash algorithm is versioned and incompatible baselines are rejected.
3. Audit documentation now states that dependency CSS, generated output, and computed runtime styles require separate visual inspection.

The first semantic screenshot then exposed a remaining fixed `height: 65px` from dependency CSS even though the adapter had reset padding and `min-height`. The adapter explicitly neutralized the inherited height, the behavior comparison remained unchanged, and both route and visual checks were rerun. Framework guidance now requires computed-style inspection of explicit dimensions, positioning, pseudo-elements, and responsive rules instead of assuming a later bundle resets them.

## Reproduction outline

Use a temporary sparse checkout at the pinned commit, create a dedicated virtual environment, install the target's locked npm graph, record a behavior baseline, build the original, apply the Skill workflow, rebuild, compare behavior signals and generated JavaScript, serve `dist`, then inspect `#/`, `#/active`, and `#/completed` in Chrome. The exact temporary checkout is intentionally not committed; the commit, target path, hash, checks, and baseline failure above are the durable evidence.
