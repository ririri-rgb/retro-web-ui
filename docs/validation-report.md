# Validation report

Date: 2026-08-27
Environment: macOS, repository-local Python virtual environment (Python 3.14.3), Node.js 25.9.0, Google Chrome (existing installation)

## Completed

- `.venv/bin/python -m unittest discover -s tests -v`: 23 tests passed after behavior, packaging, monorepo, archive, and direct theme-import regressions were added.
- Official Skill Creator `quick_validate.py`: passed inside the repository virtual environment with PyYAML installed only in that ignored environment.
- `npm run build:fixtures`: locked React/Vite, Vue/Vite, SvelteKit static-adapter, and Next App Router production builds passed.
- `npm audit --omit=dev`: zero production vulnerabilities. The fixture-only development graph currently reports three low-severity findings through SvelteKit's `cookie@0.6.0`; no moderate/high/critical findings and no non-breaking registry fix are available.
- Clean dependency installation: the host's global npm cache contained unrelated root-owned files, so no system permission was changed; `npm ci --cache .npm-cache` completed from the lockfile, followed by all four builds, production audit, and browser smoke.
- `.venv/bin/python tests/visual_smoke.py`: real ArrowDown keyboard interaction smoke and React production-build click/status smoke passed; modern + four theme desktop screenshots and two narrow responsive screenshots rendered.
- React 19/Vite 8 semantic conversion: production build passed, pre/post behavior signals were unchanged, a real click changed `aria-pressed`, label, and live status, and the Japanese utility screenshot was inspected.
- TodoMVC semantic conversion: production build passed, generated JavaScript stayed byte-identical, behavior compare was unchanged, `#/active` and `#/completed` retained selected state, and the Windows 98 screenshot was inspected.
- Manual all-image inspection: confirmed distinct Win98 bevels, XP themed states, Win7 light command hierarchy, dense Japanese utility composition, and usable narrow stacking.
- Release-stabilization rerun: clean `npm ci --cache .npm-cache`, all four locked fixture builds, production audit, 23 unit tests, both Skill validators, YAML parsing, real keyboard/click browser smoke, Markdown local-link checks, secret/local-path/history scans, and `git diff --check` passed.
- Release package rerun: two independently generated `retro-web-ui-0.1.0.zip` files were byte-identical; the checksum passed from a clean download-style directory; the extracted Skill passed both validators and contained its MIT license.

## Failure-driven iteration

Initial screenshots showed both tab panels simultaneously. Root cause: the shared `.retro-stack` display rule overrode HTML's `hidden` behavior. The fix added a scoped `[hidden] { display: none !important; }` invariant, a test assertion, and a full five-theme rerun.

Independent clean-install testing then found that the reproducible release ZIP omitted the root MIT text. A matching `skills/retro-web-ui/LICENSE` was added so a standalone Skill archive carries its license.

The final clean release build exposed an unignored SvelteKit static `build/` directory. Because CI intentionally requires a clean tree after all fixture builds, this would have blocked both main and tagged release workflows. The exact fixture output path was added to `.gitignore`, then the build and cleanliness gates were rerun.

Real-OSS testing found a behavior-guard false positive when a CSS import was inserted before an unchanged event binding. The signal hash was changed to exclude preceding source context and a regression test was added. Independent review also identified unsafe replacement of an existing bundle output; the generator now refuses it unless the caller reviews and passes `--force`.

Because hash extraction changes make earlier baselines incompatible, the signal algorithm is versioned and comparisons reject mismatched versions. A later review showed that fixed following-context still reacted to ordinary JSX class additions, so v3 hashes self-contained binding/request/form expressions instead of neighboring UI markup. TodoMVC real-OSS evidence also showed that a clean static audit can miss dependency CSS and that bundle-only integration is not a semantic conversion; both limitations are now explicit. Its first semantic result retained a dependency-owned fixed input height, so the targeted adapter and framework guidance now cover explicit dimensions and the route/visual checks were rerun.

## Not claimed

The Vue, SvelteKit, and Next integration fixtures validate detection, protection signals, and production builds, not complete runtime conversions. React has one converted runtime fixture; that does not generalize to every React component library. External OSS evidence is recorded separately when completed.
