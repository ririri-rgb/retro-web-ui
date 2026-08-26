# Windows 7 theme

Model a Windows 7 desktop utility/settings dialog, not a generic blue glass website. Aero belongs mainly to the outer frame; content stays practical and readable.

## Principles and metrics

- Reference installed `Segoe UI`, then system sans; do not distribute the font. Use about 12-13 px body/controls and a small number of hierarchy levels.
- Use roughly 5 px label/control spacing, 7 px related spacing, 11 px unrelated groups/margins, and standard compact buttons.
- Prefer thin cool-gray strokes, white list/content panes, subtle blue selection, soft control gradients, and restrained 3-5 px window rounding.
- Keep focus and disabled contrast stronger than historically weak cases when necessary for modern accessibility.

## Composition

- Primary utility: light title frame, toolbar or command bar as the main command surface, navigation pane only when categories/hierarchy justify it, details/content pane, optional primary-window status bar.
- Settings: horizontal tabs only for a small single row; use vertical categories for larger sets. Keep delayed `OK` / `Cancel` / `Apply` behavior when that is the original contract.
- Data: details list/table, grouped list, or navigation-plus-detail. Preserve sorting, selection, column, and virtualization behavior.
- Important choice: task-dialog-like main instruction and standard buttons; use a command link only when an action needs a title plus explanatory text.

## Controls and states

- Buttons use thin boundaries and restrained gradients; default/hover gain blue emphasis without becoming large CTAs.
- Fields and list views remain white and inset. Toolbars/command bars can have a pale blue-gray gradient.
- Progress uses green/blue, while passive current/context information can use a status band.
- Close/cancel semantics, keyboard menu access, tab focus, and command-link arrow keys/click behavior must remain intact.

## Semantic mappings

- Cards → categorized/grouped list, details pane, or bordered property section.
- Modern settings sidebar → navigation pane plus property page; segmented control → tabs when it switches pages.
- Large action with explanation → command link; ordinary save/cancel → standard push buttons.
- Toast → inline status for noncritical state or task dialog for an important decision.
- Dashboard → Explorer/control-panel style list and details, not translucent tiles.

## Avoid

Full-page glass/acrylic, Windows 11 large radii, oversized icons/type, borderless mobile controls, Win98 multi-bevel edges, indiscriminate ribbons or command links, and simultaneous menu+toolbar+sidebar+card layers without information need.
