#!/usr/bin/env python3
"""Unified, agent-friendly CLI for deterministic Retro Web UI operations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

if __package__:
    from . import audit_ui, behavior_guard, bundle_theme, inspect_project
    from .contracts import (
        CLI_API_VERSION,
        EXIT_ERROR,
        EXIT_INCOMPATIBLE,
        EXIT_OK,
        EXIT_REVIEW,
        MANIFEST_SCHEMA_VERSION,
        THEME_SCHEMA_VERSION,
        TOOL_VERSION,
        diagnostic,
        envelope,
    )
else:
    import audit_ui
    import behavior_guard
    import bundle_theme
    import inspect_project
    from contracts import (
        CLI_API_VERSION,
        EXIT_ERROR,
        EXIT_INCOMPATIBLE,
        EXIT_OK,
        EXIT_REVIEW,
        MANIFEST_SCHEMA_VERSION,
        THEME_SCHEMA_VERSION,
        TOOL_VERSION,
        diagnostic,
        envelope,
    )


class CLIError(Exception):
    """Expected input, environment, or safety failure."""

    def __init__(self, code: str, message: str, *, hint: Optional[str] = None, exit_code: int = EXIT_ERROR):
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.exit_code = exit_code


class CLIArgumentParser(argparse.ArgumentParser):
    """Turn usage failures into the same structured CLI error boundary."""

    def error(self, message: str) -> None:
        raise CLIError("USAGE_ERROR", message)


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_directory(value: str) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise CLIError("TARGET_NOT_DIRECTORY", f"Target is not a readable directory: {root}")
    return root


def load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CLIError(code, f"File does not exist: {path}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CLIError(code, f"Cannot read valid JSON from {path}: {error}")
    if not isinstance(value, dict):
        raise CLIError(code, f"Expected a JSON object in {path}")
    return value


def theme_digests() -> dict[str, str]:
    return {
        theme: hashlib.sha256(bundle_theme.build(theme).encode("utf-8")).hexdigest()
        for theme in bundle_theme.THEMES
    }


def check_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    manifest = load_json(path, "MANIFEST_INVALID")
    diagnostics: list[dict[str, Any]] = []
    compatible = True
    if manifest.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        compatible = False
        diagnostics.append(diagnostic(
            "MANIFEST_SCHEMA_MISMATCH",
            "error",
            f"Manifest schema {manifest.get('manifest_schema_version')!r} is incompatible with {MANIFEST_SCHEMA_VERSION}.",
            hint="Use the CLI bundled with this Skill version.",
        ))
    required = manifest.get("required_cli_api", {})
    minimum = required.get("min")
    maximum = required.get("max")
    if not isinstance(minimum, int) or not isinstance(maximum, int) or not minimum <= CLI_API_VERSION <= maximum:
        compatible = False
        diagnostics.append(diagnostic(
            "CLI_API_MISMATCH",
            "error",
            f"CLI API {CLI_API_VERSION} is outside the manifest range {minimum!r}..{maximum!r}.",
            hint="Invoke skills/retro-web-ui/scripts/retro_web_ui.py from the same Skill installation.",
        ))
    behavior = manifest.get("behavior", {})
    if behavior.get("snapshot_schema_version") != 1 or behavior.get("signal_algorithm") != behavior_guard.SIGNAL_ALGORITHM:
        compatible = False
        diagnostics.append(diagnostic(
            "BEHAVIOR_CONTRACT_MISMATCH",
            "error",
            "Manifest behavior schema or signal algorithm does not match the shared core.",
            hint="Create a fresh baseline only after installing a matching CLI and Skill.",
        ))
    themes = manifest.get("themes", {})
    expected_bundles = themes.get("bundles", {})
    actual_bundles = theme_digests()
    if themes.get("theme_schema_version") != THEME_SCHEMA_VERSION or expected_bundles != actual_bundles:
        compatible = False
        diagnostics.append(diagnostic(
            "THEME_CONTRACT_MISMATCH",
            "error",
            "Manifest theme schema or bundled asset digests do not match the shared core.",
            hint="Do not mix theme assets and CLI files from different releases.",
        ))
    if manifest.get("skill_version") != TOOL_VERSION:
        compatible = False
        diagnostics.append(diagnostic(
            "SKILL_VERSION_MISMATCH",
            "error",
            f"Skill version {manifest.get('skill_version')!r} does not match CLI version {TOOL_VERSION!r}.",
        ))
    return manifest, diagnostics, compatible


def package_directory(package: dict[str, Any]) -> str:
    parent = Path(str(package.get("path", "package.json"))).parent.as_posix()
    return "." if parent in ("", ".") else parent


def frontend_dependencies() -> set[str]:
    dependencies: set[str] = set()
    for signals in inspect_project.FRAMEWORKS.values():
        dependencies.update(signals.get("deps", set()))
    return dependencies


def discover_candidates(root: Path, workspace_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    frontend = frontend_dependencies()
    package_directories = {package_directory(package) for package in workspace_analysis.get("packages", [])}

    def static_html_evidence(package_path: str) -> Optional[str]:
        base = root if package_path == "." else root / package_path
        for current, dirs, files in os.walk(base):
            current_path = Path(current)
            relative_current = current_path.relative_to(root).as_posix()
            dirs[:] = [
                name for name in dirs
                if name not in inspect_project.EXCLUDED
                and not (current_path / name).is_symlink()
                and (current_path / name).relative_to(root).as_posix() not in package_directories - {package_path}
            ]
            for name in files:
                path = current_path / name
                if not path.is_symlink() and path.suffix.lower() in {".html", ".htm"}:
                    return f"html:{Path(relative_current, name).as_posix()}"
        return None

    for package in workspace_analysis.get("packages", []):
        dependencies = set(package.get("dependencies", []))
        package_path = package_directory(package)
        workspace_orchestrator = package_path == "." and bool(package.get("workspaces")) and not dependencies & frontend
        static_evidence = None if workspace_orchestrator else static_html_evidence(package_path)
        if dependencies & frontend or static_evidence:
            evidence = sorted(f"dependency:{name}" for name in dependencies & frontend)
            if static_evidence:
                evidence.append(static_evidence)
            candidates.append({
                "path": package_path,
                "name": package.get("name"),
                "package_manager": package.get("package_manager"),
                "evidence": evidence,
            })
    if not candidates and workspace_analysis.get("frameworks"):
        candidates.append({
            "path": ".",
            "name": None,
            "package_manager": workspace_analysis.get("package_manager"),
            "evidence": ["workspace-level-framework-signal"],
        })
    if not candidates and any(root.glob("*.htm*")):
        candidates.append({
            "path": ".",
            "name": None,
            "package_manager": None,
            "evidence": ["root-static-html"],
        })
    unique = {item["path"]: item for item in candidates}
    return [unique[path] for path in sorted(unique)]


def select_candidate(root: Path, candidates: list[dict[str, Any]], requested: Optional[str]) -> tuple[Optional[dict[str, Any]], bool]:
    if requested is None:
        if len(candidates) == 1:
            return candidates[0], False
        return None, len(candidates) > 1
    requested_path = Path(requested)
    if requested_path.is_absolute():
        try:
            normalized = requested_path.resolve().relative_to(root).as_posix()
        except ValueError:
            raise CLIError("APP_OUTSIDE_TARGET", f"Selected app is outside target: {requested_path}")
    else:
        normalized = requested_path.as_posix().rstrip("/") or "."
    matches = [item for item in candidates if item["path"] == normalized or item.get("name") == requested]
    if len(matches) == 1:
        return matches[0], False
    explicit = (root / normalized).resolve()
    try:
        explicit.relative_to(root)
    except ValueError:
        raise CLIError("APP_OUTSIDE_TARGET", f"Selected app is outside target: {explicit}")
    if explicit.is_dir():
        return {"path": normalized, "name": None, "package_manager": None, "evidence": ["explicit-selection"]}, False
    available = ", ".join(item["path"] for item in candidates) or "none detected"
    raise CLIError("APP_NOT_FOUND", f"App selection {requested!r} was not found; candidates: {available}")


def argv_for(manager: Optional[str], script: str) -> list[str]:
    if manager == "pnpm":
        return ["pnpm", script]
    if manager == "yarn":
        return ["yarn", script]
    if manager == "bun":
        return ["bun", "run", script]
    return ["npm", "run", script]


def execution_plan(analysis: dict[str, Any], fallback_manager: Optional[str] = None) -> list[dict[str, Any]]:
    managers = {package_directory(package): package.get("package_manager") for package in analysis.get("packages", [])}
    plan = []
    for purpose in sorted(analysis.get("verification_commands", {})):
        for item in analysis["verification_commands"][purpose]:
            manager = managers.get(item.get("cwd", ".")) or analysis.get("package_manager") or fallback_manager
            plan.append({
                "purpose": purpose,
                "cwd": item.get("cwd", "."),
                "manager": manager or "npm-fallback",
                "script": item["script"],
                "argv": argv_for(manager, item["script"]),
                "execution": "not-run",
            })
    return plan


def analyze_core(root: Path, requested_app: Optional[str]) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    workspace_analysis = inspect_project.detect(root)
    candidates = discover_candidates(root, workspace_analysis)
    selected, ambiguous = select_candidate(root, candidates, requested_app)
    diagnostics: list[dict[str, Any]] = []
    if ambiguous:
        diagnostics.append(diagnostic(
            "APP_SELECTION_REQUIRED",
            "review",
            "Multiple frontend applications were detected; no app was selected.",
            hint="Re-run with --app using one of the candidate paths or package names.",
        ))
    elif not candidates and selected is None:
        diagnostics.append(diagnostic(
            "NO_FRONTEND_CANDIDATE",
            "warning",
            "No frontend application candidate was detected.",
            hint="Inspect the target manually or select a nested directory with --app.",
        ))
    selected_path = selected["path"] if selected else None
    analysis = inspect_project.detect((root / selected_path).resolve()) if selected_path else workspace_analysis
    result = {
        "selection": {
            "workspace_root": str(root),
            "candidates": candidates,
            "selected": selected,
            "ambiguous": ambiguous,
        },
        "analysis": analysis,
        "verification_plan": execution_plan(analysis, selected.get("package_manager") if selected else None),
        "agent_hints": [
            "Treat detected dependencies and source markers as evidence, not proof that a rendered surface uses them.",
            "Run target-native verification commands only after selecting the intended application and reviewing their side effects.",
            "Keep semantic conversion and visual fidelity decisions in the Skill workflow.",
        ],
    }
    return result, diagnostics, ambiguous


def git_observation(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    git = shutil.which("git")
    if not git:
        diagnostics.append(diagnostic("GIT_UNAVAILABLE", "warning", "Git is not available on PATH."))
        return {"available": False, "repository": False}, diagnostics
    probe = subprocess.run([git, "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if probe.returncode != 0:
        return {"available": True, "repository": False}, diagnostics
    git_root = probe.stdout.strip()
    status = subprocess.run([git, "-C", str(root), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True)
    if status.returncode != 0:
        diagnostics.append(diagnostic("GIT_STATUS_FAILED", "warning", status.stderr.strip() or "Could not read git status."))
        return {"available": True, "repository": True, "root": git_root, "status_available": False}, diagnostics
    entries = [line for line in status.stdout.splitlines() if line]
    if entries:
        diagnostics.append(diagnostic(
            "GIT_DIRTY",
            "warning",
            f"The selected repository has {len(entries)} changed or untracked path(s).",
            hint="Preserve unrelated work and review the final diff before conversion.",
        ))
    return {"available": True, "repository": True, "root": git_root, "dirty": bool(entries), "entry_count": len(entries)}, diagnostics


def doctor_from_analysis(root: Path, analysis: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    diagnostics: list[dict[str, Any]] = []
    git_result, git_diagnostics = git_observation(root)
    diagnostics.extend(git_diagnostics)
    managers = sorted({
        item.get("package_manager")
        for item in analysis["selection"]["candidates"]
        if item.get("package_manager")
    })
    manager_status = []
    for manager in managers:
        executable = shutil.which(manager)
        manager_status.append({"name": manager, "available": executable is not None, "executable": executable})
        if executable is None:
            diagnostics.append(diagnostic(
                "PACKAGE_MANAGER_UNAVAILABLE",
                "warning",
                f"Detected package manager {manager!r} is not available on PATH.",
                hint="Install it only if the selected target's own verification requires it.",
            ))
    manifest, manifest_diagnostics, compatible = check_manifest(skill_root() / "manifest.json")
    diagnostics.extend(manifest_diagnostics)
    python_path = Path(sys.executable)
    python_name = python_path.stem.lower()
    python_runnable = (
        python_path.is_file()
        and os.access(python_path, os.X_OK)
        and python_name.startswith(("python", "pypy"))
    )
    return {
        "python": {
            "version": list(sys.version_info[:3]),
            "executable": sys.executable,
            "runnable": python_runnable,
            "runtime_kind": "interpreter" if python_runnable else "embedded",
        },
        "git": git_result,
        "package_managers": manager_status,
        "selection": analysis["selection"],
        "manifest": {"path": str(skill_root() / "manifest.json"), "compatible": compatible, "skill_version": manifest.get("skill_version")},
        "verification_plan": analysis["verification_plan"],
    }, diagnostics, not compatible


def doctor_core(root: Path, requested_app: Optional[str]) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    analysis, diagnostics, ambiguous = analyze_core(root, requested_app)
    result, doctor_diagnostics, incompatible = doctor_from_analysis(root, analysis)
    diagnostics.extend(doctor_diagnostics)
    return result, diagnostics, ambiguous or incompatible


def ensure_output_parent(output: Path) -> None:
    if not output.parent.is_dir():
        raise CLIError(
            "OUTPUT_PARENT_MISSING",
            f"Output parent does not exist: {output.parent}",
            hint="Create and review the parent directory before writing.",
        )


def resolve_output(value: str) -> Path:
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise CLIError("OUTPUT_IS_SYMLINK", f"Refusing to write through a symlink: {raw}")
    return raw.resolve()


def write_if_safe(output: Path, content: str, force: bool) -> tuple[str, bool, Optional[str]]:
    ensure_output_parent(output)
    previous_sha256: Optional[str] = None
    if output.exists():
        try:
            existing = output.read_text(encoding="utf-8")
        except OSError as error:
            raise CLIError("OUTPUT_UNREADABLE", f"Cannot read existing output {output}: {error}")
        if existing == content:
            return "current", False, None
        if not force:
            raise CLIError(
                "OUTPUT_EXISTS",
                f"Refusing to overwrite different existing file: {output}",
                hint="Review the existing file, then pass --force if replacement is intended.",
            )
        previous_sha256 = hashlib.sha256(existing.encode("utf-8")).hexdigest()
    try:
        output.write_text(content, encoding="utf-8")
    except OSError as error:
        raise CLIError("OUTPUT_WRITE_FAILED", f"Cannot write {output}: {error}")
    return "written", True, previous_sha256


def info_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    path = Path(args.manifest).expanduser().resolve() if args.manifest else skill_root() / "manifest.json"
    manifest, diagnostics, compatible = check_manifest(path)
    result = {
        "version": TOOL_VERSION,
        "cli_api_version": CLI_API_VERSION,
        "manifest_path": str(path),
        "manifest_compatible": compatible,
        "behavior": manifest.get("behavior"),
        "theme_schema_version": manifest.get("themes", {}).get("theme_schema_version"),
        "theme_bundle_sha256": theme_digests(),
    }
    status = "ok" if compatible else "incompatible"
    return envelope("info", status, result, diagnostics), EXIT_OK if compatible else EXIT_INCOMPATIBLE


def analyze_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    root = resolve_directory(args.target)
    result, diagnostics, ambiguous = analyze_core(root, args.app)
    return envelope("analyze", "review_required" if ambiguous else "ok", result, diagnostics, target=str(root)), EXIT_REVIEW if ambiguous else EXIT_OK


def doctor_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    root = resolve_directory(args.target)
    result, diagnostics, blocked = doctor_core(root, args.app)
    incompatible = not result["manifest"]["compatible"]
    status = "incompatible" if incompatible else "review_required" if blocked else "ok"
    code = EXIT_INCOMPATIBLE if incompatible else EXIT_REVIEW if blocked else EXIT_OK
    return envelope("doctor", status, result, diagnostics, target=str(root)), code


def behavior_snapshot_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    root = resolve_directory(args.target)
    output = resolve_output(args.output)
    if not args.allow_in_project:
        try:
            output.relative_to(root)
        except ValueError:
            pass
        else:
            raise CLIError(
                "OUTPUT_INSIDE_TARGET",
                f"Behavior baseline output is inside the target repository: {output}",
                hint="Use a temporary path outside the target, or pass --allow-in-project after review.",
            )
    snapshot = behavior_guard.snapshot(root)
    content = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
    action, changed, previous_sha256 = write_if_safe(output, content, args.force)
    result = {
        "output": str(output),
        "action": action,
        "changed": changed,
        "signal_bearing_files": len(snapshot["files"]),
        "snapshot_schema_version": snapshot["schema_version"],
        "signal_algorithm": snapshot["signal_algorithm"],
    }
    if previous_sha256:
        result["replaced_sha256"] = previous_sha256
    return envelope("behavior.snapshot", "ok", result, target=str(root), read_only=False), EXIT_OK


def behavior_compare_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    root = resolve_directory(args.target)
    baseline_path = Path(args.baseline).expanduser().resolve()
    baseline = load_json(baseline_path, "BASELINE_INVALID")
    if baseline.get("schema_version") != 1:
        result = {
            "status": "incompatible-baseline",
            "protected_signal_changes": [],
            "removed_signal_count": 0,
            "message": f"Baseline schema {baseline.get('schema_version')!r} is incompatible with schema 1.",
        }
    else:
        result = behavior_guard.compare(baseline, behavior_guard.snapshot(root))
    if result["status"] == "incompatible-baseline":
        diagnostics = [diagnostic("BASELINE_INCOMPATIBLE", "error", result["message"], hint="Create a new baseline with this CLI version.")]
        return envelope("behavior.compare", "incompatible", result, diagnostics, target=str(root)), EXIT_INCOMPATIBLE
    if result["protected_signal_changes"]:
        diagnostics = [diagnostic(
            "BEHAVIOR_REVIEW_REQUIRED",
            "review",
            "Protected source signals changed; inspect every addition and removal.",
        )]
        return envelope("behavior.compare", "review_required", result, diagnostics, target=str(root)), EXIT_REVIEW
    return envelope("behavior.compare", "ok", result, target=str(root)), EXIT_OK


def theme_list_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    digests = theme_digests()
    result = {
        "theme_schema_version": THEME_SCHEMA_VERSION,
        "themes": [{"id": theme, "bundle_sha256": digests[theme]} for theme in bundle_theme.THEMES],
    }
    return envelope("theme.list", "ok", result), EXIT_OK


def theme_bundle_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    content = bundle_theme.build(args.theme)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if args.check and not args.output:
        raise CLIError("OUTPUT_REQUIRED", "--check requires --output")
    if args.check and args.force:
        raise CLIError("CONFLICTING_OPTIONS", "--check and --force cannot be combined")
    result: dict[str, Any] = {"theme": args.theme, "bundle_sha256": digest, "bytes": len(content.encode("utf-8"))}
    if not args.output:
        result["css"] = content
        return envelope("theme.bundle", "ok", result), EXIT_OK
    output = resolve_output(args.output)
    if args.check:
        if not output.is_file():
            result.update({"output": str(output), "current": False})
            diagnostics = [diagnostic("THEME_BUNDLE_MISSING", "review", f"Theme bundle is missing: {output}")]
            return envelope("theme.bundle", "review_required", result, diagnostics), EXIT_REVIEW
        try:
            current = output.read_text(encoding="utf-8") == content
        except OSError as error:
            raise CLIError("OUTPUT_UNREADABLE", f"Cannot read {output}: {error}")
        result.update({"output": str(output), "current": current})
        if not current:
            diagnostics = [diagnostic("THEME_BUNDLE_STALE", "review", f"Theme bundle differs from the shared core: {output}")]
            return envelope("theme.bundle", "review_required", result, diagnostics), EXIT_REVIEW
        return envelope("theme.bundle", "ok", result), EXIT_OK
    action, changed, previous_sha256 = write_if_safe(output, content, args.force)
    result.update({"output": str(output), "action": action, "changed": changed})
    if previous_sha256:
        result["replaced_sha256"] = previous_sha256
    return envelope("theme.bundle", "ok", result, read_only=False), EXIT_OK


def audit_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    root = resolve_directory(args.target)
    result = audit_ui.audit(root, args.theme)
    review = bool(result["findings"])
    diagnostics = []
    if review:
        diagnostics.append(diagnostic(
            "STATIC_AUDIT_REVIEW_REQUIRED",
            "review",
            f"Static audit reported {len(result['findings'])} finding group(s).",
            hint="Review source, computed styles, screenshots, and runtime behavior; do not suppress blindly.",
        ))
    status = "review_required" if review else "ok"
    return envelope("audit", status, result, diagnostics, target=str(root)), EXIT_REVIEW if review else EXIT_OK


def verify_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    root = resolve_directory(args.target)
    analysis, analysis_diagnostics, ambiguous = analyze_core(root, args.app)
    doctor, doctor_diagnostics, doctor_blocked = doctor_from_analysis(root, analysis)
    diagnostics = analysis_diagnostics + doctor_diagnostics
    result: dict[str, Any] = {
        "analysis": analysis,
        "doctor": doctor,
        "audit": None,
        "behavior": None,
        "target_commands_executed": False,
        "limitations": [
            "This command does not run target package scripts, browser flows, or visual review.",
            "A clean static result does not prove behavior preservation or theme fidelity.",
        ],
    }
    review = ambiguous or doctor_blocked
    incompatible = not doctor["manifest"]["compatible"]
    if args.theme:
        audit_result = audit_ui.audit(root if not analysis["selection"]["selected"] else Path(analysis["analysis"]["root"]), args.theme)
        result["audit"] = audit_result
        if audit_result["findings"]:
            review = True
            diagnostics.append(diagnostic("STATIC_AUDIT_REVIEW_REQUIRED", "review", "Static UI audit has findings."))
    else:
        diagnostics.append(diagnostic("THEME_NOT_CHECKED", "warning", "No --theme was supplied, so static theme integration was not audited."))
    if args.baseline:
        baseline = load_json(Path(args.baseline).expanduser().resolve(), "BASELINE_INVALID")
        if baseline.get("schema_version") != 1:
            comparison = {"status": "incompatible-baseline", "message": "Baseline schema does not match schema 1.", "protected_signal_changes": []}
        else:
            comparison = behavior_guard.compare(baseline, behavior_guard.snapshot(root))
        result["behavior"] = comparison
        if comparison["status"] == "incompatible-baseline":
            incompatible = True
            diagnostics.append(diagnostic("BASELINE_INCOMPATIBLE", "error", comparison["message"]))
        elif comparison["protected_signal_changes"]:
            review = True
            diagnostics.append(diagnostic("BEHAVIOR_REVIEW_REQUIRED", "review", "Protected source signals changed."))
    else:
        diagnostics.append(diagnostic("BEHAVIOR_NOT_COMPARED", "warning", "No --baseline was supplied, so behavior signals were not compared."))
    status = "incompatible" if incompatible else "review_required" if review else "ok"
    code = EXIT_INCOMPATIBLE if incompatible else EXIT_REVIEW if review else EXIT_OK
    return envelope("verify", status, result, diagnostics, target=str(root)), code


def add_common_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", nargs="?", default=".", help="repository or workspace root")
    parser.add_argument("--app", help="frontend app path or package name when discovery is ambiguous")
    parser.add_argument("--json", action="store_true", help="emit one versioned JSON object on stdout")


def build_parser() -> argparse.ArgumentParser:
    parser = CLIArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {TOOL_VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)

    info = commands.add_parser("info", help="show CLI/Skill/theme contract versions")
    info.add_argument("--manifest", help="Skill manifest to validate; defaults to the bundled manifest")
    info.add_argument("--json", action="store_true")
    info.set_defaults(handler=info_command)

    analyze = commands.add_parser("analyze", help="inspect project structure without editing")
    add_common_target(analyze)
    analyze.set_defaults(handler=analyze_command)

    doctor = commands.add_parser("doctor", help="diagnose local tools, git state, app selection, and version contracts")
    add_common_target(doctor)
    doctor.set_defaults(handler=doctor_command)

    behavior = commands.add_parser("behavior", help="snapshot or compare protected source signals")
    behavior_commands = behavior.add_subparsers(dest="behavior_command", required=True)
    snapshot = behavior_commands.add_parser("snapshot", help="write an explicit hashed behavior artifact")
    snapshot.add_argument("target")
    snapshot.add_argument("--output", "-o", required=True)
    snapshot.add_argument("--force", action="store_true")
    snapshot.add_argument("--allow-in-project", action="store_true")
    snapshot.add_argument("--json", action="store_true")
    snapshot.set_defaults(handler=behavior_snapshot_command)
    compare = behavior_commands.add_parser("compare", help="compare a baseline with current source")
    compare.add_argument("baseline")
    compare.add_argument("target")
    compare.add_argument("--json", action="store_true")
    compare.set_defaults(handler=behavior_compare_command)

    theme = commands.add_parser("theme", help="inspect or bundle deterministic theme assets")
    theme_commands = theme.add_subparsers(dest="theme_command", required=True)
    theme_list = theme_commands.add_parser("list", help="list themes and bundle digests")
    theme_list.add_argument("--json", action="store_true")
    theme_list.set_defaults(handler=theme_list_command)
    theme_bundle = theme_commands.add_parser("bundle", help="render one deterministic CSS bundle")
    theme_bundle.add_argument("theme", choices=bundle_theme.THEMES)
    theme_bundle.add_argument("--output", "-o")
    theme_bundle.add_argument("--check", action="store_true")
    theme_bundle.add_argument("--force", action="store_true")
    theme_bundle.add_argument("--json", action="store_true")
    theme_bundle.set_defaults(handler=theme_bundle_command)

    audit = commands.add_parser("audit", help="find static modern-style residue and integration gaps")
    audit.add_argument("target", nargs="?", default=".")
    audit.add_argument("--theme", choices=bundle_theme.THEMES, required=True)
    audit.add_argument("--json", action="store_true")
    audit.set_defaults(handler=audit_command)

    verify = commands.add_parser("verify", help="aggregate read-only deterministic verification evidence")
    add_common_target(verify)
    verify.add_argument("--theme", choices=bundle_theme.THEMES)
    verify.add_argument("--baseline")
    verify.set_defaults(handler=verify_command)
    return parser


def render_human(document: dict[str, Any]) -> None:
    command = document["command"]
    result = document["result"]
    if result is None:
        for item in document["diagnostics"]:
            print(f"{item['severity']}: {item['code']}: {item['message']}", file=sys.stderr)
        return
    if command == "theme.bundle" and "css" in result:
        print(result["css"], end="")
        return
    if command == "info":
        print(f"retro-web-ui {result['version']} (CLI API {result['cli_api_version']})")
        print(f"manifest compatible: {'yes' if result['manifest_compatible'] else 'no'}")
    elif command == "analyze":
        selection = result["selection"]
        print(f"workspace: {selection['workspace_root']}")
        print("candidates: " + (", ".join(item["path"] for item in selection["candidates"]) or "none"))
        print(f"selected: {(selection['selected'] or {}).get('path', 'none')}")
        analysis = result["analysis"]
        print("frameworks: " + (", ".join(item["name"] for item in analysis["frameworks"]) or "not detected"))
        print("styling: " + (", ".join(item["name"] for item in analysis["styling"]) or "not detected"))
    elif command == "doctor":
        print(f"manifest compatible: {'yes' if result['manifest']['compatible'] else 'no'}")
        print(f"git repository: {'yes' if result['git'].get('repository') else 'no'}")
        print(f"verification commands: {len(result['verification_plan'])}")
    elif command == "behavior.snapshot":
        print(f"{result['action']}: {result['output']} ({result['signal_bearing_files']} signal-bearing files)")
    elif command == "behavior.compare":
        print(result["status"])
        for item in result.get("protected_signal_changes", []):
            print(f"{item['file']}: {item['signal']} -{item['removed']} +{item['added']}")
        print(result["message"])
    elif command == "theme.list":
        for item in result["themes"]:
            print(f"{item['id']}  {item['bundle_sha256']}")
    elif command == "theme.bundle":
        print(f"{result.get('action', 'checked')}: {result.get('output', result['theme'])}")
    elif command == "audit":
        print(f"{result['theme']}: {result['status']}")
        for item in result["findings"]:
            print(f"{item['severity']}: {item['file']}: {item['check']} ({item['count']})")
    elif command == "verify":
        print(f"verify: {document['status']}")
        print(f"target commands executed: {result['target_commands_executed']}")
        print(f"suggested commands: {len(result['analysis']['verification_plan'])}")
    for item in document["diagnostics"]:
        print(f"{item['severity']}: {item['code']}: {item['message']}", file=sys.stderr)


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    raw_arguments = list(argv) if argv is not None else sys.argv[1:]
    wants_json = "--json" in raw_arguments
    args: Optional[argparse.Namespace] = None
    try:
        args = parser.parse_args(raw_arguments)
        document, exit_code = args.handler(args)
    except CLIError as error:
        command = getattr(args, "command", None) or next((value for value in raw_arguments if not value.startswith("-")), "unknown")
        item = diagnostic(error.code, "error", str(error), hint=error.hint)
        document = envelope(command, "error", None, [item])
        exit_code = error.exit_code
    except Exception as error:  # pragma: no cover - defensive CLI boundary
        command = getattr(args, "command", "unknown") if args is not None else "unknown"
        item = diagnostic("INTERNAL_ERROR", "error", f"Unexpected {type(error).__name__}: {error}")
        document = envelope(command, "error", None, [item])
        exit_code = EXIT_ERROR
    if wants_json or (args is not None and getattr(args, "json", False)):
        print(json.dumps(document, indent=2, ensure_ascii=False))
    else:
        render_human(document)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
