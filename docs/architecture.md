# Architecture

Retro Web UI separates judgment from deterministic mechanics.

1. **Repository analyzer:** gathers package, file, framework, styling, command, and risk evidence without editing.
2. **Behavior baseline:** hashes normalized event, network, auth, route, state, storage, form, and framework-binding signals without storing source excerpts.
3. **Theme specifications:** separate semantic mapping, structural language, and visual tokens. Shared CSS primitives remain namespaced.
4. **Context-aware transformation:** Codex edits markup/components because semantic restructuring cannot be made safe with a universal regex/AST rewrite.
5. **Verification:** target-native checks, protected-signal comparison, runtime flows, static audit, visual inspection, and diff review.

AST tooling is deliberately not a required runtime dependency. Framework parsers can improve a future adapter, but full-file regeneration creates formatting and source-boundary risk. Any adapter should use syntax-aware source ranges, preserve bindings, and fall back to a reviewable plan when uncertain.

The Skill is the distributable product under `skills/retro-web-ui/`. Repository-root tests, screenshots, research, and release tooling validate that product without loading all evidence into Codex context during ordinary use.
