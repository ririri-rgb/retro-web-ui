# Verification workflow

## Command discovery

Use `inspect_project.py` to report declared package scripts and likely commands. Run only commands that exist or are clearly supported by the repository. Preserve the repository's package manager and lockfile.

## Build and static checks

Run existing build, typecheck, lint, and test commands. Record unavailable checks as unavailable, not passed. Review compiler warnings, hydration errors, and browser console errors.

## Behavior checks

Cover at least one critical path and each touched interaction type. Favor existing end-to-end tests. Otherwise perform focused manual checks without mutating production data. Compare handler wiring, request construction, form semantics, route targets, storage keys, loading/error states, focus order, and keyboard activation.

## Visual checks

Capture representative screens at the application's normal desktop viewport and at an existing responsive breakpoint. Inspect clipping, overflow, focus, labels, contrast, disabled states, modern-style residue, theme-specific structure, and Japanese text fit.

After a shared theme-kit change, render the showcase for all four themes. A screenshot is evidence of appearance, not behavior.

## Diff review

Use `git diff --check`, inspect changed-file scope, run the behavior comparison, and search for secrets or generated artifacts before delivery. Explain every necessary logic-adjacent change.

## Regression set

Re-run the failing case, at least one earlier passing fixture, and a structurally different fixture. For framework-specific changes, also run the generic static fixture. Record best-effort and unsupported outcomes in compatibility documentation.
