# CLI + Skill validation report

Date: 2026-08-27

Baseline: immutable public `v1.0.0` tag at `14c365b3f3132dc0898b417447108cc417c22c53`

Release source version: `1.1.0`

## Architecture result

The established v1.0 detector, behavior guard, theme bundler, and static audit remain the canonical deterministic implementations. The Skill directory is now also an installable Python package. A unified CLI consumes those modules, legacy script entry points remain available, and `retro_web_ui.core` exposes the same functions for a future GUI.

The CLI owns repeatable observation, explicit artifacts, contract checks, and structured reporting. Codex retains surface selection when intent is contextual, semantic mapping, markup edits, application-specific SSR/portal/CSS repair, target-command execution decisions, runtime interpretation, accessibility judgment, and visual fidelity. There is no universal `convert` command.

The detailed A-D inventory and safety rationale are in [CLI and Skill responsibility boundary](cli-boundary.md).

## CLI contract exercised

- `info`: bundled Skill manifest, CLI API, behavior schema/algorithm, theme schema, and four full bundle digests.
- `analyze`: explicit frontend candidates, selected app, framework/style/rendering/component/risk evidence, and non-executed verification argv.
- `doctor`: Python, Git, package-manager availability, selection, and manifest compatibility.
- `behavior snapshot/compare`: explicit non-overwriting artifact and review/incompatibility exit semantics.
- `theme list/bundle`: deterministic CSS, digest, idempotence, check, and non-overwrite behavior.
- `audit`: static review signals without claiming visual proof.
- `verify`: a read-only aggregation which does not install dependencies or execute target scripts.

All JSON commands emit one envelope at schema version 1. Exit codes are `0` complete, `1` review required, `2` input/safety error, `3` contract incompatibility, with `4` reserved for future explicitly requested command execution failures.

## Validation completed

- Python unit suite: 47 tests after CLI, monorepo, package-manager metadata, output safety, symlink-scope, manifest mismatch, and packaging assertions were added; the previous 32 v1 tests remain present.
- Python 3.10 isolated-venv pass: unit suite and repository Skill validator passed. CI retains the Python 3.9 minimum job and adds CLI packaging jobs on Linux, macOS, and Windows with Python 3.12.
- Repository validator and official Skill Creator validator: passed.
- Pushed candidate CI: final reviewed implementation commit `b0c9107` passed Python 3.9 minimum validation, the full Linux fixture/browser job, and reproducible packaging/clean-install jobs on Linux, macOS, and Windows with Python 3.12 ([run 33069368303](https://github.com/ririri-rgb/retro-web-ui/actions/runs/33069368303)).
- Five locked production fixture builds: React/Vite, React/MUI/Emotion, Vue/Bootstrap, SvelteKit adapter-static, and Next App Router passed; Next remained request-time SSR.
- Production npm audit: zero vulnerabilities. The full development-tree audit reports low-severity `GHSA-pxg6-pf52-xh8x` through SvelteKit's `cookie@0.6.0`; npm's offered fix is a breaking SvelteKit downgrade, and the dependency is absent from every released CLI/Skill artifact.
- Browser gates: showcase and React interaction passed; MUI portal, Bootstrap lifecycle, Svelte hydration, Next initial SSR/hydration, external CDP interaction, Escape/focus behavior, and browser warning/error checks passed.
- CLI workflow across six converted fixtures: static HTML, React, MUI, Vue, SvelteKit, and Next produced compatible manifests, explicit baselines, unchanged behavior comparison, and structured verification. Vue and Next correctly retained static review findings for intentionally present upstream utility/class collision probes; runtime gates supplied the required review evidence rather than suppressing the warnings.
- Python wheel and sdist: two independent builds were byte-identical after deterministic tar/gzip metadata normalization. A new temporary venv installed the wheel offline with `--no-deps`; the console entry point, manifest check, static-app analysis, and `retro_web_ui.core` import passed.
- Standalone Skill archive: still packages the full Skill, license, manifest, CLI, shared facade, references, scripts, and assets while excluding hidden/generated metadata.

## Real OSS reuse

The existing MIT-licensed TodoMVC case was re-cloned at pinned commit `ff43b02e59dfa604386bb382034b2cd07c2bcd8a`. On its real multi-application repository, the CLI selected `examples/javascript-es6`, detected it as static/Vanilla with npm build/dev argv, reported a clean Git state and compatible manifest, wrote a 10-file hashed baseline outside the checkout, and compared it unchanged.

This rerun validates the new deterministic CLI boundary against the same real target used for the v1 semantic Windows 98 evidence. It does not replace or inflate the original runtime/visual claim, and it does not claim that the unmodified upstream checkout is already converted.

## Failures found and generalized fixes

| Failure | Classification | Generalized correction |
| --- | --- | --- |
| Standard setuptools sdist differed between identical builds | Packaging/reproducibility | Normalize tar order, mtime, uid/gid, and gzip metadata in the release packager; verify two independent outputs |
| Dependency-only app discovery omitted nested Vanilla TodoMVC | Framework/project detection | Detect HTML entry evidence inside each package without crossing into another nested package; keep workspace orchestrators from becoming false app candidates |
| `verify` scanned the same tree twice through `analyze` and `doctor` | Performance/agent efficiency | Reuse the analyzed result for doctor observations in the aggregate command |
| Source symlinks could point outside the selected target | Safety/scope | Skip symlinked directories and files in detector, behavior, and audit walkers; add a regression test |
| Vue/Next converted fixtures still trigger modern-class heuristics | Static audit boundary | Keep review findings visible; resolve them with inspected scoped adapters and passing runtime/computed-style evidence rather than adding suppressions |

## Packaging, security, and license boundary

The installed CLI has zero third-party runtime dependencies. `setuptools` and `build` are release-only tooling. The wheel contains the MIT license, Skill manifest/instructions, original CSS-only theme assets, references, and shared Python modules; it contains no fixture dependency graph, browser, proprietary Windows asset, credential, or local checkout path. The source distribution excludes tests and fixture content. Standalone Skill ZIP packaging remains independently reproducible.

The repository's locked browser/framework harness has one known low-severity development-only advisory (`GHSA-pxg6-pf52-xh8x`, `cookie@0.6.0` through `@sveltejs/kit@2.70.3`). A forced npm remediation would downgrade SvelteKit incompatibly, so the release records the issue instead of applying an unverified lockfile override. Production audit remains clean and none of this dependency graph is packaged.

## Performance and agent experience

One `analyze` result now supplies app candidates, framework/rendering/style evidence, warnings, and executable argv instead of requiring the agent to rediscover each item. One `verify` call combines contract, Git/environment, static audit, and behavior comparison without rescanning the project or running commands. JSON diagnostics include stable codes and next-action hints, and ambiguous monorepos stop with `APP_SELECTION_REQUIRED` rather than producing a confident mixed-app plan.

No cache was added: current fixtures and the real TodoMVC target complete quickly enough that cache invalidation and cleanup risk would outweigh the measured benefit.

## Known limitations

- CLI analysis and audit remain static evidence with documented false-positive/false-negative boundaries.
- Target-native build/test/runtime commands are suggested but not executed. This is a deliberate safety boundary, not a missing automatic conversion feature.
- Semantic conversion, visual quality, accessibility, and application-specific portal/SSR/CSS repair remain best-effort Skill work.
- npm is exercised in current fixtures and TodoMVC; pnpm is backed by the v1 naive-ui-admin record plus synthetic metadata coverage, yarn by mixed-workspace tests, and Bun by detection/argv tests only. The CLI does not install any package manager.
- Local clean packaging is validated on macOS/Python 3.14 and the core suite on Python 3.10. The pushed candidate passed Linux/macOS/Windows packaging and clean-install jobs on Python 3.12 plus the Python 3.9 minimum job.

## GUI readiness and release recommendation

The future GUI can call the shared Python facade or the CLI JSON API for analysis, diagnostics, behavior artifacts, themes, and verification. The GUI must still present app selection, explicit artifact writes, review-required states, and user-authorized target commands; it must not label static evidence as conversion success. Semantic edits and visual judgment still require the Skill/agent unless a future bounded adapter is separately proven.

The architecture is backward-compatible and adds a substantial new interface without removing the v1 Skill workflow, so the approved release line is the minor release `v1.1.0`, rather than a major version. The report was reviewed, the source version was promoted to `1.1.0`, and publication remains gated by the release commit CI, tag/version check, reproducible packages, and GitHub Release verification.
