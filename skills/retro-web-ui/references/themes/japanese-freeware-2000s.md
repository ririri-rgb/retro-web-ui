# Japanese Freeware 2000s theme

Target practical Japanese Windows utilities from roughly 2000 through the early 2010s: feature-rich, conventional, and task-oriented rather than fashionable retro web design. This is an information architecture, not a national color palette.

## Principles and metrics

- Use an installed Japanese-capable stack such as Meiryo or MS UI Gothic, then system sans; do not distribute proprietary fonts. Target 11-12 px with compact line height.
- Build dense layouts from 3/4/6 px relationships, short Japanese labels, aligned rows, right-aligned numeric fields, and little decorative whitespace.
- Use a neutral fixed-window-like frame, white/pale work panes, one-pixel boundaries, minimal shadow, and almost no large-radius treatment.
- Density must expose useful state, not merely make text tiny. Preserve logical grouping, keyboard order, and readable Japanese glyphs.

## Composition

- Primary utility: menu bar, small text/icon toolbar, split client area, operational list/tree/table/log pane, and persistent segmented status bar.
- Settings: many conventional controls organized as tabs, category tree/list plus property page, or simple/advanced modes. Use short group-box legends and bottom-right `OK` / `キャンセル` / `適用` / `ヘルプ` patterns when semantics fit.
- File/transfer/queue tools: dual panes or list/detail, sortable columns, progress row, log, and counts/mode in the status bar.
- Small operations: dedicated compact dialogs instead of expanding the main screen into a large marketing flow.

## Controls and states

- Prefer checkbox, radio, combo/select, text/numeric/spin field, `...` browse button, tabs, list/tree/table, small toolbar buttons, and conventional add/remove/up/down rows.
- Preserve access keys, shortcuts, validation, sorting, selection, resize/reorder, and keyboard traversal.
- Use compact status text or a log for background information; use an explicit error/confirmation dialog for critical feedback.
- Use original CSS and text affordances unless the target already contains clearly redistributable icons.

## Semantic mappings

- Modern card → group box, option page, list/detail region, or log/status pane.
- SaaS settings sidebar → dense property sheet or category tree plus right pane.
- Toggle/chip/segmented control → checkbox, combo, tabs, or radio group according to single/multiple selection.
- Dashboard cards → details table, grouped operational counters, queue, or dual-pane view.
- Toast → status line/log for background information, dialog for important outcomes.
- Large CTA → standard command row. Keep a simple mode and detailed mode when the original product already distinguishes novice/advanced tasks.

## Avoid

Neon, CRT, scanlines, glitch/Y2K fashion, red-white “Japan” symbolism, anime/game theming, glossy web banners, pixel fonts everywhere, giant icons, excessive whitespace, 12+ px radii, modern marketing cards, and merely translating a SaaS dashboard into Japanese. Verify clipping at desktop width and an existing responsive breakpoint.
