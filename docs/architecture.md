# Architecture

Retro Web UI separates judgment from deterministic mechanics through a shared Python core, an agent-friendly CLI, and the Codex Skill.

1. **Repository analyzer:** gathers package, file, framework, styling, command, and risk evidence without editing.
2. **Behavior baseline:** hashes normalized event, network, auth, route, state, storage, form, and framework-binding signals without storing source excerpts.
3. **Theme specifications:** separate semantic mapping, structural language, and visual tokens. Shared CSS primitives remain namespaced.
4. **Unified CLI:** exposes the same core as `info`, `analyze`, `doctor`, `behavior`, `theme`, `audit`, and read-only `verify` commands with one versioned JSON envelope.
5. **Context-aware transformation:** the Skill consumes CLI evidence and Codex edits markup/components because semantic restructuring cannot be made safe with a universal regex/AST rewrite.
6. **Verification:** the CLI aggregates deterministic evidence; Codex selects safe target-native checks and performs runtime flows, static-finding interpretation, visual inspection, and diff review.

AST tooling is deliberately not a required runtime dependency. Framework parsers can improve a future adapter, but full-file regeneration creates formatting and source-boundary risk. Any adapter should use syntax-aware source ranges, preserve bindings, and fall back to a reviewable plan when uncertain.

The Skill directory under `skills/retro-web-ui/` is also the Python package source. Existing v1.0 helper modules remain the canonical deterministic implementations, the unified CLI calls them, and `retro_web_ui.core` exposes the same functions for future GUI reuse. Legacy script entry points remain available without duplicating detector, behavior, audit, or theme logic.

The CLI never performs universal conversion or implicit package-script execution. Detailed A-D classification, safety rules, and the rationale for keeping semantic/visual reasoning in Codex are recorded in [CLI and Skill responsibility boundary](cli-boundary.md).
