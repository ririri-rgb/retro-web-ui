# Semantic mappings

Use these as decision rules, not automatic substitutions.

| Modern pattern | Desktop-era mapping | Preserve |
| --- | --- | --- |
| Card | group box, inset panel, or list-view section | heading relationship and click target |
| Toggle switch | checkbox | boolean value, disabled state, callback, accessible name |
| Segmented control | property-sheet tabs or radio group | single selection and keyboard semantics |
| Settings sidebar | tabbed property sheet or category list plus pane | route/deep-link behavior and state |
| Large CTA | standard default push button | submit/action behavior and emphasis |
| Modal | desktop dialog with title bar and command row | focus trap, escape/close, validation |
| Dashboard cards | report/list view, grouped controls, or summary fields | navigation and data meaning |
| Toast | status bar for transient state or dialog for blocking state | announcement and dismissal |
| Command palette | menu/toolbar plus dialog when search is essential | shortcut and filtering behavior |
| Pill/chip filters | checkboxes, combo box, tabs, or list filters | multi/single selection semantics |

Do not turn every region into a fake window. Use one primary application frame, then group boxes, panes, toolbars, menus, tabs, lists, and dialogs according to meaning.
