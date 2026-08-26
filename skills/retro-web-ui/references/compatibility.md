# Compatibility model

Support is evidence-based and layered:

- **Verified:** automated fixture plus build/static checks and visual inspection.
- **Supported with conditions:** architecture is covered, but component-library or SSR details require manual integration.
- **Best-effort:** detection and scoped CSS work, while semantic restructuring depends heavily on project internals.
- **Unsupported safely:** reliable conversion would require changing behavior or inaccessible rendering internals.

Record verified target results in that target repository's existing documentation or the final task report; do not upgrade a claim from this reference alone. Closed Shadow DOM, canvas/WebGL-only UI, cross-origin iframe contents, binary-generated frontend bundles without source, and native desktop applications are not safe automatic targets.
