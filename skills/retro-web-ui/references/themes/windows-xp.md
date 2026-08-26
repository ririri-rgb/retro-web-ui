# Windows XP theme

Express Luna-era themed common controls rather than recoloring Windows 98. Keep classic utility structure while making states and hierarchy more graphical.

## Principles and metrics

- Use an installed Tahoma/system fallback around 11-12 px. Do not bundle Tahoma.
- Keep utility density, but increase internal padding and unrelated-group spacing slightly beyond Windows 98.
- Use saturated active title chrome, pale warm dialog surfaces, white list/property areas, blue boundaries, and a green progress accent.
- Mild 2-4 px control/tab curvature is appropriate. It should read as a themed bitmap-like edge, not a modern rounded card.

## Composition

- Primary window: stronger colored non-client frame, menu/toolbar where meaningful, classic client and status regions.
- Settings: property sheets remain primary. A category/task pane can replace a modern sidebar when it represents navigation rather than decoration.
- Data: compact details list by default; grouped or tile-like lists only when icons and secondary descriptions carry real meaning.
- Dialog: warm client surface, clear default command, bottom-right command row, and compact progress/message areas.

## Controls and states

- Provide visible normal, hot, pressed, selected, disabled, and focused states across buttons, tabs, checks, radios, fields, and list rows.
- Default buttons can gain a blue emphasis ring. Active tabs use a shaped shoulder and warm highlight rather than a Win98 hard double-bevel.
- Progress may be green and segmented/smooth. List selection stays a strong blue.
- Use CSS borders/gradients for control chrome; never embed `.msstyles`, Luna bitmaps, Start-button imagery, or shell icons.

## Semantic mappings

- Card → titled property group or task-pane section.
- Settings sidebar → XP category/task pane plus property page, or classic tabs for a small set.
- Toggle → checkbox; segmented control → themed tabs or radio group.
- Dashboard cards → grouped details/tile list; blocking toast → message dialog; background activity → progress/status area.
- Large CTA → standard themed push button.

## Avoid

Win98 gray controls with only a blue title bar, Vista/7 glass, large glossy web buttons, neon Start-button mimicry, excessive rounding, bubbly Web 2.0 decoration, and a full fake XP desktop around an ordinary application.
