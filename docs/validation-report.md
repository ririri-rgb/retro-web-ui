# Validation report

Date: 2026-08-27
Environment: macOS, repository-local Python virtual environment (Python 3.14.3), Node.js 25.9.0, existing Google Chrome. CI targets Python 3.9/3.12 and Node.js 22.

## Final local gates

- `npm ci --cache .npm-cache`: clean lockfile installation passed. The full fixture-only development graph reports three low-severity findings through SvelteKit's `cookie@0.6.0`; no moderate/high/critical finding and no non-breaking registry fix is available.
- `npm run build:fixtures`: five locked workspaces passed: React/Vite, React/MUI/Emotion, Vue/Bootstrap, SvelteKit adapter-static, and Next App Router. The Next route was confirmed as request-time dynamic SSR.
- `npm audit --omit=dev --audit-level=moderate`: zero production vulnerabilities.
- `.venv/bin/python -m unittest discover -s tests -v`: 32 tests passed, including repository Markdown-link resolution.
- Repository validator and official Skill Creator `quick_validate.py`: both passed inside the repository virtual environment.
- `.venv/bin/python tests/visual_smoke.py`: static showcase interaction, React interaction, modern + four theme desktop renders, and two narrow renders passed.
- `.venv/bin/python tests/runtime_smoke.py`: MUI, Bootstrap, SvelteKit hydration, and Next SSR/hydration in-app assertions passed. A separate dependency-free Chrome DevTools Protocol driver then repeated normal-page form/dialog interactions from outside each application and checked browser warning/error events.
- Generated showcase and framework screenshots were byte-identical to the reviewed repository images.
- Two independently packaged standalone Skill archives were byte-identical (`a3dc108134508b9e8bf2033e489fd0373a3c0857605e252c4aeef4f2921c245b`); checksum verification and validation after extraction passed.
- `git diff --check`, tracked/ignored-file review, local-path scan, secret-pattern scan, and archive checks passed before commit.

## Runtime assertions

| Fixture | Assertions |
| --- | --- |
| React/MUI/Emotion | controlled input/save, tab and checkbox state, portal theme scope, computed dialog radius, Escape close, focus return, warning/error-free browser events |
| Vue/Bootstrap | `v-model`, trim/save/live status, actual `shown.bs.modal` and `hidden.bs.modal` lifecycle, scoped override of upstream `!important`, warning/error-free browser events |
| SvelteKit | prerendered output hydration, `bind:value`/`bind:checked`, form/trim/live status, warning/error-free browser events |
| Next/Radix/Tailwind | theme/content in initial request-time server HTML, client hydration, controlled form, portal theme scope, Tailwind collision override, Escape/focus return, warning/error-free browser events |

The in-application selftests catch framework state and computed-style details. The external CDP driver prevents those selftests from being the sole behavior evidence: it performs a second interaction pass against the normal URL and captures `Runtime`, console, and browser log errors/warnings.

## Real OSS evidence

- TodoMVC Vanilla ES6: pinned MIT checkout, semantic Windows 98 conversion, original/themed build, byte-identical generated JavaScript, unchanged behavior signals, hash-route state, and manual screenshot review. See [real-oss-todomvc.md](real-oss-todomvc.md).
- naive-ui-admin authentication surface: pinned MIT checkout, original/converted builds, real demo login and route transition, body theme cleanup on the unconverted dashboard, normal/narrow manual visual review. This is a dated manual record, not a CI fixture. See [real-oss-naive-ui-admin.md](real-oss-naive-ui-admin.md).

## Failure-driven improvements

- Shared CSS overrode native `hidden`: fixed under the theme root and regression-tested across all themes.
- Neighboring UI/import edits changed behavior hashes: self-contained expression hashing removed the false positives; the signal algorithm is versioned.
- Multiline/framework-specific bindings and several logic-adjacent contracts were missed: behavior guard v4 added React/Vue/Svelte/Svelte 5/Angular/inline/property event forms, History API, state setters/aliases, timers/subscriptions, form/framework bindings, ARIA, and test selectors.
- Bootstrap utility `!important` survived source order: a narrow theme-scoped adapter and computed-style check were added.
- MUI deprecated passthrough props attached attributes to the wrong wrapper: current slot APIs and final-DOM assertions replaced them.
- Arbitrary modal sleeps were flaky: observable library lifecycle events are awaited.
- A partial naive-ui-admin conversion leaked a body theme into the next route: the permanent root was localized and portal-host mirroring became component-lifecycle scoped.
- Chrome stderr alone did not substantiate console/hydration claims: logging plus external CDP warning/error capture was added.
- The first Linux CI run exposed a Chrome-profile cleanup race after a successful Svelte interaction. The driver now waits for browser exit and retries deletion of its exact temporary profile before the gate completes.

## Visual evidence boundary

The repository images were generated from current production builds and manually inspected. CI regenerates current renders and uploads them as workflow artifacts, but it does not use a pixel-diff threshold; visual acceptance remains a human judgment. A clean source audit is not treated as visual proof.

## Environment and storage

No browser, SDK, container, or system package was installed. Existing Chrome and repository-local Node dependencies were reused. The naive-ui-admin clone, pnpm stores, and builds occupied about 2.5 GB and were removed after the screenshot/evidence record was retained. Final one-run screenshot directories were also removed. The ignored local npm cache is about 206 MB and node_modules about 469 MB.

## Release state

`v0.1.0` remains the immutable public baseline. These changes are unreleased development on main; no `v1.0.0` tag or GitHub Release was created in this phase.
