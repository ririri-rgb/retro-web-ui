# CLI and Skill responsibility boundary

This document records the evidence-based boundary used for the post-`v1.0.0` CLI + Skill architecture. It is an engineering contract, not a claim that static tooling can perform semantic conversion.

## v1.0 inventory

| Existing capability | Class | Owner after extraction | Reason |
| --- | --- | --- | --- |
| Repository walking, package/lockfile inspection, framework/style/risk signals | A/B | Shared core + CLI `analyze` | Repeatable evidence collection; heuristics remain labelled as evidence |
| Verification-command discovery | B | Shared core + CLI analysis/verify plan | Command inference is repeatable, but execution and failure interpretation remain contextual |
| Hashed behavior snapshot and comparison | A | Shared core + CLI `behavior` | Stable schema and signal algorithm already reject incompatible baselines |
| Theme CSS assembly and digest | A | Shared core + CLI `theme` | Byte-deterministic and safe to check independently |
| Static modern-style residue audit | B | Shared core + CLI `audit` | Useful heuristic; false positives and false negatives require review |
| Runtime, git, package-manager, and Skill/CLI contract diagnostics | A/B | CLI `doctor` | Deterministic observations with explicit warnings |
| Read-only aggregation of analysis, audit, and behavior comparison | A/B | CLI `verify` | One stable agent-facing result without silently executing project scripts |
| Choosing the conversion surface and interpreting component meaning | C | Skill / Codex | A repository can contain several valid surfaces and ambiguous UI intent |
| SSR/client boundary, portal lifecycle, and CSS-collision repair strategy | C | Skill / Codex | Detection can expose risk, but safe repair is application-specific |
| Semantic remapping, markup recomposition, theme fidelity, and visual review | D | Skill / Codex | These require contextual and visual reasoning |

Class A is pure deterministic work, B is mostly deterministic evidence or heuristics, C is contextual judgment, and D is semantic/visual reasoning.

## Deliberate exclusions

There is no universal `convert` command. The CLI does not claim semantic equivalence, theme fidelity, accessibility, or framework-wide support. It also does not install dependencies or run inferred package scripts implicitly. Target-native builds and tests can create artifacts, contact services, or depend on credentials, so the Skill presents the structured execution plan and chooses safe commands in context.

## Shared core shape

The distributable Skill directory is also the Python package source. The established v1.0 helper modules remain the canonical implementations; the unified CLI calls those modules, legacy script entry points remain compatible, and `retro_web_ui.core` exposes the same functions for a future GUI or another Python caller. Human and JSON renderers consume the same command result.

The CLI JSON envelope, Skill manifest, behavior snapshot schema, signal algorithm, and theme asset digests are versioned independently. This prevents a nominal package version match from hiding an incompatible baseline or modified theme asset.

## Safety contract

- `info`, `analyze`, `doctor`, `behavior compare`, `theme list`, `audit`, and `verify` are read-only.
- `behavior snapshot` and `theme bundle --output` are the only write operations.
- New CLI writes require an existing parent directory, refuse a different existing file unless `--force` is explicit, and recommend behavior artifacts outside the target repository.
- Multiple detected frontend applications require `--app`; the CLI does not guess.
- Static warnings are evidence for review, not proof of failure or success.
- The Skill invokes the bundled CLI path and checks its manifest before conversion instead of silently trusting an unrelated executable on `PATH`.

