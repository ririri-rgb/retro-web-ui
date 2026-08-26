# Windows 98 theme

Aim for a compact Win32 utility/property-sheet language, not a nostalgic web desktop. System roles and edge direction matter more than one fixed gray palette.

## Principles and metrics

- Use a small installed system-font stack, roughly 11-12 CSS pixels, tight line height, and sentence-case labels. Do not bundle MS Sans Serif.
- Build spacing from 4/6/8 px relationships. Align labels and fields; use borders and grouping rather than whitespace as the main separator.
- Model face, field, highlight, shadow, dark shadow, selection, caption, and disabled roles. A raised edge is light on top/left and dark on bottom/right; a sunken edge reverses that reading.
- Keep controls about 22-24 px high and standard command buttons around 70-80 px wide unless text requires more.

## Composition

- Primary utility: title bar, optional menu bar, optional small toolbar, client region, and segmented status bar.
- Settings: classic one-row property tabs, group boxes, aligned form rows, and `OK` / `Cancel` / `Apply` at bottom right.
- Data: white sunken list/tree/details view with a simple header and strong selected row.
- Dialog: one decision or task, compact body, explicit command row. Use modal dialogs for blocking feedback and the status bar for passive state.

## Controls and states

- Use square push buttons, native checkboxes/radios, select/combo treatment, text fields, list boxes, tabs, progress bars, and scrollable panes.
- Show normal, hover when useful, pressed, selected, focused, default, disabled, and validation states without changing interaction semantics.
- Preserve an obvious focus rectangle. A default submit button may have an additional outer border.
- Use hard two-level bevels for the window/button family and sunken fields. Do not flatten only one control family.

## Semantic mappings

- Card → group box, sunken pane, or list-view section.
- Modern sidebar → tabs for a small settings set; tree/list plus property pane for a large set.
- Toggle → checkbox; segmented control → classic tabs or radio buttons.
- Dashboard metrics → labeled values or details list; toast → status segment or dialog.
- Large CTA → standard default push button without changing its submit/action role.

## Avoid

Large radii, floating cards, glass blur, soft ambient shadows, oversized hero text, pill filters, generous SaaS whitespace, hover-only discovery, and decorative fake desktop icons. Do not recreate the Windows desktop or Start menu unless the application's meaning requires an operating-system shell.
