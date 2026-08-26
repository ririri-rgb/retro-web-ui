---
name: retro-web-ui
description: Transform existing web application interfaces into Windows 98, Windows XP, Windows 7, or Japanese freeware 2000s desktop styles while preserving behavior. Use for repository-level retro UI conversions, not for greenfield mockups or bitmap-only artwork.
---

# Retro Web UI

Restyle an existing web application without changing what it does. Treat visual fidelity and behavior preservation as equal requirements.

## Start with evidence

1. Resolve the requested theme to exactly one of `windows-98`, `windows-xp`, `windows-7`, or `japanese-freeware-2000s`. If the wording is ambiguous, infer the closest explicit theme and state the assumption.
2. Run `scripts/inspect_project.py <repo> --json` and inspect the application entry points, styling architecture, package scripts, existing tests, and current git status.
3. Read [behavior-preservation.md](references/behavior-preservation.md) and [verification.md](references/verification.md). Read only the selected file under [themes/](references/themes/) and the relevant sections of [framework-guides.md](references/framework-guides.md).
4. Before editing, create a hashed behavior baseline with `scripts/behavior_guard.py snapshot <repo> --output <temporary-json>`. Keep the baseline outside the target repository unless the user asks to retain evidence.

## Transform the UI

- Preserve API calls, authentication, routing, state semantics, persistence, validation, data formats, and handler bodies. Reuse existing props, bindings, names, IDs, form actions, ARIA, and test selectors.
- Prefer a scoped root such as `data-retro-theme="windows-98"`. Generate the CSS starter with `scripts/bundle_theme.py <theme> --output <project-path>` and adapt its import to the detected stack.
- Apply semantic mappings from [semantic-mapping.md](references/semantic-mapping.md). Recompose markup only when the modern structure conflicts with the chosen desktop UI language; retain the original control's meaning and accessible interaction.
- Use native semantic elements first. A visual tab that changes panels still needs keyboard-accessible tab behavior; a toggle converted to a checkbox must preserve its checked state and callback.
- Do not copy Microsoft fonts, icons, bitmaps, DLL resources, or screenshots into the project. Use the bundled CSS-only primitives and system-font fallbacks. Read [licensing.md](references/licensing.md) before adding third-party material.
- Do not mass-rewrite source with regex. Scripts provide detection, deterministic assets, and verification; Codex performs context-aware edits.

## Verify in a loop

1. Run the target repository's existing build, typecheck, lint, and tests when available.
2. Compare the behavior baseline with `scripts/behavior_guard.py compare <baseline> <repo>`. Investigate every protected-signal change; the tool is a guardrail, not proof of equivalence.
3. Exercise important flows: navigation, forms, validation, state changes, loading/error states, keyboard use, and API request construction. Do not perform real destructive or production actions without authorization.
4. Run `scripts/audit_ui.py <repo> --theme <theme>` and review warnings rather than blindly suppressing them.
5. Start the application when practical, inspect representative viewport screenshots, and iterate on clipping, focus, density, modern-style residue, and theme-specific structure.
6. Review `git diff` for unrelated or logic-side changes. Re-test the failure case, a previously passing case, another application shape when available, and all four themes after shared CSS changes.

## Report honestly

Classify any failure using [compatibility.md](references/compatibility.md) as specification, instruction, framework integration, CSS collision, component-library conflict, semantic interpretation, behavior preservation, visual verification, environment, or fundamentally difficult. Generalize repeatable fixes into the skill; document unsafe or unverified cases instead of claiming support. Summarize changed UI structure, protected behavior evidence, commands run, visual coverage, and remaining limitations.
