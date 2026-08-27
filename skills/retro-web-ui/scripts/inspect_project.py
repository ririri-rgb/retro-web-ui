#!/usr/bin/env python3
"""Detect web stacks and verification hooks without modifying the target repository."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Optional

EXCLUDED = {".git", ".hg", ".svn", "node_modules", "dist", "build", ".next", ".nuxt", ".svelte-kit", "coverage", "vendor"}
LOCKFILES = {
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "bun.lock": "bun",
    "bun.lockb": "bun",
    "package-lock.json": "npm",
}
FRAMEWORKS = {
    "next": {"deps": {"next"}, "files": {"next.config.js", "next.config.mjs", "next.config.ts"}},
    "nuxt": {"deps": {"nuxt"}, "files": {"nuxt.config.js", "nuxt.config.ts"}},
    "sveltekit": {"deps": {"@sveltejs/kit"}, "files": {"svelte.config.js", "svelte.config.ts"}},
    "react": {"deps": {"react", "react-dom"}, "extensions": {".jsx", ".tsx"}},
    "vue": {"deps": {"vue"}, "extensions": {".vue"}},
    "svelte": {"deps": {"svelte"}, "extensions": {".svelte"}},
    "angular": {"deps": {"@angular/core"}, "files": {"angular.json"}},
    "astro": {"deps": {"astro"}, "extensions": {".astro"}},
    "vite": {"deps": {"vite"}, "files": {"vite.config.js", "vite.config.ts", "vite.config.mjs"}},
}
STYLING = {
    "tailwind": {"tailwindcss", "@tailwindcss/vite", "@tailwindcss/postcss"},
    "bootstrap": {"bootstrap", "react-bootstrap", "bootstrap-vue", "bootstrap-vue-next"},
    "mui": {"@mui/material", "@material-ui/core"},
    "chakra": {"@chakra-ui/react"},
    "ant-design": {"antd", "ant-design-vue"},
    "vuetify": {"vuetify"},
    "radix-shadcn": {"@radix-ui/react-dialog", "@radix-ui/react-tabs", "shadcn"},
    "styled-components": {"styled-components"},
    "emotion": {"@emotion/react", "@emotion/styled"},
    "naive-ui": {"naive-ui"},
    "vuestic": {"vuestic-ui"},
    "element-plus": {"element-plus"},
}
SOURCE_EXTENSIONS = {".html", ".htm", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".vue", ".svelte", ".astro", ".css", ".scss", ".sass", ".less"}


def walk_files(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.startswith(".cache"))
        current_path = Path(current)
        for name in sorted(files):
            yield current_path / name


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def read_package(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def dependency_names(package: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        values = package.get(key, {})
        if isinstance(values, dict):
            result.update(str(name) for name in values)
    return result


def package_manager_for(package_dir: Path, root: Path) -> Optional[str]:
    current = package_dir
    while True:
        for lockfile, manager in LOCKFILES.items():
            if (current / lockfile).is_file():
                return manager
        if current == root or root not in current.parents:
            return None
        current = current.parent


def command_for(manager: Optional[str], script: str) -> str:
    prefix = {"npm": "npm run", "pnpm": "pnpm", "yarn": "yarn", "bun": "bun run"}.get(manager, "npm run")
    return f"{prefix} {script}"


def detect(root: Path) -> dict[str, Any]:
    all_files = list(walk_files(root))
    rel_files = {relative(path, root) for path in all_files}
    basenames = {path.name for path in all_files}
    extensions: dict[str, int] = {}
    for path in all_files:
        if path.suffix in SOURCE_EXTENSIONS:
            extensions[path.suffix] = extensions.get(path.suffix, 0) + 1

    package_paths = [path for path in all_files if path.name == "package.json"]
    packages = []
    combined_deps: set[str] = set()
    aliases = {
        "build": ("build",),
        "test": ("test", "test:unit", "test:e2e"),
        "lint": ("lint",),
        "typecheck": ("typecheck", "type-check", "check"),
        "dev": ("dev", "start"),
    }
    commands: dict[str, list[dict[str, str]]] = {}
    for path in package_paths:
        data = read_package(path)
        deps = dependency_names(data)
        scripts = data.get("scripts", {}) if isinstance(data.get("scripts", {}), dict) else {}
        package_dir = path.parent
        package_manager = package_manager_for(package_dir, root)
        package_cwd = relative(package_dir, root) if package_dir != root else "."
        combined_deps.update(deps)
        package_commands = {}
        for purpose, names in aliases.items():
            for script in names:
                if script in scripts:
                    entry = {"cwd": package_cwd, "command": command_for(package_manager, script), "script": script}
                    commands.setdefault(purpose, []).append(entry)
                    package_commands.setdefault(purpose, []).append(entry["command"])
        packages.append({
            "path": relative(path, root),
            "name": data.get("name"),
            "private": bool(data.get("private", False)),
            "package_manager": package_manager,
            "dependencies": sorted(deps),
            "scripts": {str(key): str(value) for key, value in sorted(scripts.items())},
            "verification_commands": package_commands,
        })

    framework_results = []
    for name, signals in FRAMEWORKS.items():
        evidence = []
        matched_deps = sorted(signals.get("deps", set()) & combined_deps)
        matched_files = sorted(signals.get("files", set()) & basenames)
        matched_extensions = sorted(ext for ext in signals.get("extensions", set()) if extensions.get(ext))
        evidence.extend(f"dependency:{item}" for item in matched_deps)
        evidence.extend(f"file:{item}" for item in matched_files)
        evidence.extend(f"extension:{item}({extensions[item]})" for item in matched_extensions)
        if evidence:
            score = min(1.0, 0.35 * len(matched_deps) + 0.35 * len(matched_files) + 0.2 * len(matched_extensions))
            framework_results.append({"name": name, "confidence": round(max(score, 0.35), 2), "evidence": evidence})

    styling_results = []
    for name, deps in STYLING.items():
        matches = sorted(deps & combined_deps)
        if matches:
            styling_results.append({"name": name, "evidence": [f"dependency:{item}" for item in matches]})
    if "components.json" in basenames and not any(item["name"] == "radix-shadcn" for item in styling_results):
        styling_results.append({"name": "radix-shadcn", "evidence": ["file:components.json"]})

    static_html = sorted(path for path in rel_files if path.endswith((".html", ".htm")))
    if static_html and not framework_results:
        framework_results.append({"name": "static-html-or-vanilla", "confidence": 0.7, "evidence": [f"html:{static_html[0]}"]})

    risks = []
    rendering_evidence: dict[str, list[str]] = {}
    architecture_evidence: dict[str, list[str]] = {}

    def add_evidence(collection: dict[str, list[str]], name: str, evidence: str) -> None:
        values = collection.setdefault(name, [])
        if evidence not in values and len(values) < 8:
            values.append(evidence)

    virtual_dependencies = {
        "@tanstack/react-virtual",
        "react-window",
        "react-virtualized",
        "vue-virtual-scroller",
        "svelte-virtual-list",
    }
    if combined_deps & virtual_dependencies:
        for dependency in sorted(combined_deps & virtual_dependencies):
            add_evidence(architecture_evidence, "virtualized-ui", f"dependency:{dependency}")
    route_dependencies = {"react-router", "react-router-dom", "vue-router", "@angular/router"}
    for dependency in sorted(combined_deps & route_dependencies):
        add_evidence(architecture_evidence, "route-driven-ui", f"dependency:{dependency}")
    portal_dependencies = {"@radix-ui/react-dialog", "@radix-ui/react-popover", "@mui/material", "naive-ui"}
    for dependency in sorted(combined_deps & portal_dependencies):
        add_evidence(architecture_evidence, "portals-or-overlays", f"dependency:{dependency}")
    risk_patterns = {
        "shadow-dom": ("attachShadow", "customElements.define"),
        "canvas-or-webgl": ("<canvas", "getContext(\"webgl", "getContext('webgl"),
        "cross-origin-iframe": ("<iframe",),
        "bootstrap-js-bindings": ("data-bs-toggle", "data-bs-target", "data-bs-dismiss"),
        "tailwind-generated-classes": ("@tailwind", '@import "tailwindcss"', "@source"),
    }
    for path in all_files:
        if path.suffix not in SOURCE_EXTENSIONS or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        path_evidence = f"file:{relative(path, root)}"
        lower_name = path.name.lower()
        if re.match(r".+\.module\.(?:css|scss|sass|less)$", lower_name):
            if not any(item["name"] == "css-modules" for item in styling_results):
                styling_results.append({"name": "css-modules", "evidence": [path_evidence]})
        if path.suffix.lower() in {".scss", ".sass"} and not any(item["name"] == "sass" for item in styling_results):
            styling_results.append({"name": "sass", "evidence": [path_evidence]})
        if "<style scoped" in text and not any(item["name"] == "scoped-css" for item in styling_results):
            styling_results.append({"name": "scoped-css", "evidence": [path_evidence]})

        source_markers = {
            "client-islands": ("'use client'", '"use client"'),
            "request-time-ssr": ("force-dynamic", "getServerSideProps", "adapter-node"),
            "static-generation-or-prerender": ("prerender = true", "adapter-static", "output: 'export'", 'output: "export"'),
            "async-loaded-ui": ("React.lazy(", "defineAsyncComponent(", "import("),
        }
        for model, markers in source_markers.items():
            if any(marker in text for marker in markers):
                add_evidence(rendering_evidence, model, path_evidence)

        architecture_markers = {
            "portals-or-overlays": ("createPortal(", ".Portal", "<Teleport", "<Dialog", "data-bs-toggle=\"modal\""),
            "controlled-or-two-way-binding": ("v-model", "bind:value", "bind:checked", "onChange=", "formControlName"),
            "route-driven-ui": ("useRouter(", "useRoute(", "vue-router", "$page", "goto("),
            "virtualized-ui": ("useVirtualizer(", "VirtualList", "virtual-scroll", "virtualized"),
        }
        for architecture, markers in architecture_markers.items():
            if any(marker in text for marker in markers):
                add_evidence(architecture_evidence, architecture, path_evidence)
        for risk, patterns in risk_patterns.items():
            if any(pattern in text for pattern in patterns):
                item = next((entry for entry in risks if entry["name"] == risk), None)
                if item is None:
                    item = {"name": risk, "files": []}
                    risks.append(item)
                if len(item["files"]) < 8:
                    item["files"].append(relative(path, root))

    package_manager = None
    for lockfile, manager in LOCKFILES.items():
        if (root / lockfile).is_file():
            package_manager = manager
            break

    return {
        "schema_version": 2,
        "root": str(root.resolve()),
        "package_manager": package_manager,
        "packages": packages,
        "frameworks": sorted(framework_results, key=lambda item: (-item["confidence"], item["name"])),
        "styling": sorted(styling_results, key=lambda item: item["name"]),
        "rendering_models": [
            {"name": name, "evidence": evidence}
            for name, evidence in sorted(rendering_evidence.items())
        ],
        "component_architecture": [
            {"name": name, "evidence": evidence}
            for name, evidence in sorted(architecture_evidence.items())
        ],
        "source_extensions": dict(sorted(extensions.items())),
        "verification_commands": commands,
        "risk_signals": sorted(risks, key=lambda item: item["name"]),
        "notes": [
            "Detection is evidence, not a guarantee that a dependency is used by the rendered screen.",
            "Inspect each workspace independently before editing a monorepo.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="repository root")
    parser.add_argument("--json", action="store_true", help="emit JSON (default is a short human summary)")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    result = detect(root)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"root: {result['root']}")
        print(f"package manager: {result['package_manager'] or 'not detected'}")
        print("frameworks: " + (", ".join(item["name"] for item in result["frameworks"]) or "not detected"))
        print("styling: " + (", ".join(item["name"] for item in result["styling"]) or "not detected"))
        print("rendering: " + (", ".join(item["name"] for item in result["rendering_models"]) or "not detected"))
        print("components: " + (", ".join(item["name"] for item in result["component_architecture"]) or "not detected"))
        print("verification: " + (", ".join(result["verification_commands"]) or "not declared"))
        print("risks: " + (", ".join(item["name"] for item in result["risk_signals"]) or "none detected"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
