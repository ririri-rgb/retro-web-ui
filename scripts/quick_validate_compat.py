#!/usr/bin/env python3
"""Dependency-free repository check compatible with the core Agent Skills shape."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("SKILL.md frontmatter is not closed")
    values = {}
    for raw in text[4:end].splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            raise ValueError(f"invalid frontmatter line: {raw}")
        key, value = raw.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate(skill: Path) -> list[str]:
    errors = []
    skill_file = skill / "SKILL.md"
    if not skill_file.is_file():
        return ["missing SKILL.md"]
    text = skill_file.read_text(encoding="utf-8")
    try:
        values = frontmatter(text)
    except ValueError as error:
        return [str(error)]
    name = values.get("name", "")
    description = values.get("description", "")
    if not NAME_RE.fullmatch(name):
        errors.append("name must use lowercase letters, digits, and hyphens")
    if name != skill.name:
        errors.append(f"name {name!r} does not match folder {skill.name!r}")
    if not description or len(description) > 1024:
        errors.append("description must be present and at most 1024 characters")
    if "TODO" in text or "[TODO" in text:
        errors.append("unfinished placeholder in SKILL.md")
    for target in LINK_RE.findall(text):
        if "://" not in target and not target.startswith("#") and not target.endswith("/"):
            resolved = (skill / target).resolve()
            if not resolved.exists():
                errors.append(f"broken local link: {target}")
    for path in skill.rglob("*"):
        if path.is_file() and path.stat().st_size > 5 * 1024 * 1024:
            errors.append(f"asset exceeds 5 MiB: {path.relative_to(skill)}")
    openai = skill / "agents" / "openai.yaml"
    if openai.exists():
        yaml_text = openai.read_text(encoding="utf-8")
        match = re.search(r"^\s*short_description:\s*[\"'](.+?)[\"']\s*$", yaml_text, re.M)
        if not match or not 25 <= len(match.group(1)) <= 64:
            errors.append("agents/openai.yaml short_description must be quoted and 25-64 characters")
        default = re.search(r"^\s*default_prompt:\s*[\"'](.+?)[\"']\s*$", yaml_text, re.M)
        if not default or f"${name}" not in default.group(1):
            errors.append("default_prompt must explicitly mention the skill")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", type=Path)
    args = parser.parse_args()
    errors = validate(args.skill.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Skill is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
