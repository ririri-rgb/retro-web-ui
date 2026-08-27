# CLI workflow and contract

Use the bundled CLI for deterministic evidence and artifacts. Run it with the same Python environment used for the target work:

```bash
python /path/to/retro-web-ui/scripts/retro_web_ui.py info --json
python /path/to/retro-web-ui/scripts/retro_web_ui.py analyze /path/to/app --json
```

An installed package exposes the equivalent `retro-web-ui` command. Prefer the bundled path during Skill execution so an unrelated executable on `PATH` cannot silently supply incompatible behavior or theme assets. `info --json` must report `manifest_compatible: true` before creating a baseline.

## Commands

- `info [--manifest PATH]`: CLI API, behavior contract, theme schema, and bundle digest compatibility.
- `analyze TARGET [--app PATH_OR_NAME]`: framework, rendering, styling, component/risk evidence, candidate applications, and target-native verification argv.
- `doctor TARGET [--app ...]`: Python, Git state, detected package-manager availability, app selection, and Skill/CLI manifest compatibility.
- `behavior snapshot TARGET --output FILE`: explicit hashed artifact write. It refuses target-local output unless `--allow-in-project` is deliberate, refuses symlink outputs, and refuses a different existing file unless `--force` is deliberate. A forced replacement reports the prior SHA-256 digest.
- `behavior compare BASELINE TARGET`: read-only protected-signal comparison.
- `theme list`: four theme IDs and deterministic bundle digests.
- `theme bundle THEME [--output FILE] [--check | --force]`: deterministic CSS output with the same symlink/non-overwrite safety.
- `audit TARGET --theme THEME`: read-only static residue/integration heuristic.
- `verify TARGET [--app ...] [--theme ...] [--baseline ...]`: read-only aggregation of analysis, doctor, audit, and behavior evidence. It never installs dependencies or runs target scripts.

There is no automatic `convert` command. Codex selects and edits the UI surface, preserves bindings/contracts, resolves framework-specific collisions, and performs runtime and visual judgment.

## JSON envelope

Every supported `--json` invocation writes exactly one JSON object to stdout:

```json
{
  "schema_version": 1,
  "tool": {"name": "retro-web-ui", "version": "...", "cli_api_version": 1},
  "command": "analyze",
  "status": "ok",
  "result": {},
  "diagnostics": [],
  "meta": {"read_only": true, "target": "/absolute/target"}
}
```

Diagnostics have stable `code`, `severity`, and `message` fields, with optional `path` and `hint`. Treat detected dependencies as evidence rather than runtime proof. Project-relative evidence paths use forward slashes; canonical roots are absolute in `meta.target` and the relevant analysis result.

## Exit codes

| Code | Meaning | Required Skill response |
| ---: | --- | --- |
| `0` | Command completed; warnings can still be present | Read diagnostics and continue |
| `1` | Review required | Inspect ambiguity, static findings, or behavior changes before continuing |
| `2` | Invalid input, unavailable file, or refused unsafe write | Correct the command or obtain explicit authority; do not bypass safety silently |
| `3` | CLI/Skill/baseline contract incompatibility | Use matching files or create a fresh baseline after resolving the mismatch |
| `4` | Reserved for an explicitly requested target-command execution failure | The current read-only `verify` command does not emit this code |

## CLI unavailable

If the unified CLI cannot start but the v1 helper scripts are present, use `inspect_project.py`, `behavior_guard.py`, `bundle_theme.py`, and `audit_ui.py` as a compatibility fallback and disclose that unified `doctor`, `verify`, and JSON-envelope checks were unavailable. If Python itself is unavailable, perform manual inspection but do not claim that behavior snapshot/comparison or deterministic verification passed. Do not download or install a different CLI without normal dependency and authorization checks.
