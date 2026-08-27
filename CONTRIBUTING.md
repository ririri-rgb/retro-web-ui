# Contributing

Contributions should improve behavior preservation, evidence-backed compatibility, theme fidelity, accessibility, or documentation without broadening claims beyond tests.

1. Create a focused branch and keep unrelated changes out of the diff.
2. Add or update a fixture that exposes the problem.
3. Classify the root cause before changing the Skill, reference, script, or shared CSS.
4. Create a local environment with `python3 -m venv .venv`; run Python commands through `.venv/bin/python` (`.venv\\Scripts\\python` on Windows).
5. With Node.js 22+, run `npm ci`, `npm run build:fixtures`, and `npm audit --omit=dev --audit-level=moderate`.
6. Run `.venv/bin/python -m unittest discover -s tests -v` and `.venv/bin/python scripts/quick_validate_compat.py skills/retro-web-ui`.
7. After shared CSS changes, run `.venv/bin/python tests/visual_smoke.py`, inspect every generated image, and include regenerated screenshots when appearance intentionally changes.
8. For CLI or packaging changes, build twice with `scripts/package_cli.py` and compare/install them with `tests/package_smoke.py`.
9. Record new compatibility evidence and limitations honestly.
10. Do not contribute extracted Microsoft assets or third-party material without explicit redistribution rights and notices.

Pull requests should explain the behavior invariant, affected themes/frameworks, verification commands, visual evidence, and any remaining risk.
