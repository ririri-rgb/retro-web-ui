# Research basis

Research was performed on 2026-08-26. Primary and canonical sources were preferred.

## Codex and Agent Skills

- [OpenAI: Build skills](https://developers.openai.com/codex/skills) defines `SKILL.md`, progressive disclosure, optional scripts/references, and Skill/plugin distribution.
- [OpenAI skills repository](https://github.com/openai/skills) provides the official Skill Creator and examples.
- [Agent Skills specification](https://agentskills.io/) documents the interoperable folder format.
- Public structures compared: [anthropics/skills](https://github.com/anthropics/skills), [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills), [github/awesome-copilot](https://github.com/github/awesome-copilot), [expo/skills](https://github.com/expo/skills), [supabase/agent-skills](https://github.com/supabase/agent-skills), and [cloudflare/skills](https://github.com/cloudflare/skills).

The selected layout keeps one self-contained distributable Skill and repository-level tests/docs. It follows progressive disclosure, uses root-level clean validation, and avoids copying source from repositories whose subtree licenses differ or whose root license is unclear.

## Historical Windows UI

- Microsoft [DrawEdge](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-drawedge) and [GetSysColor](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getsyscolor) establish role-based raised/sunken edges and system colors.
- The archived [Windows XP visual styles article](https://learn.microsoft.com/en-us/archive/msdn-magazine/2001/november/new-graphical-interface-enhance-your-programs-with-new-windows-xp-shell-features) documents themed common controls, hot states, and XP list-view changes.
- The Windows 7-era UX Guide covers [fonts](https://learn.microsoft.com/en-us/windows/win32/uxguide/vis-fonts), [layout](https://learn.microsoft.com/en-us/windows/win32/uxguide/vis-layout), [tabs](https://learn.microsoft.com/en-us/windows/win32/uxguide/ctrl-tabs), [list views](https://learn.microsoft.com/en-us/windows/win32/uxguide/ctrl-list-views), [toolbars](https://learn.microsoft.com/en-us/windows/win32/uxguide/cmd-toolbars), [dialogs](https://learn.microsoft.com/en-us/windows/win32/uxguide/win-dialog-box), and [status bars](https://learn.microsoft.com/en-us/windows/win32/uxguide/ctrl-status-bars).

## Japanese freeware UI

- [Sakura Editor's historical feature screenshots](https://sakura-editor.github.io/intro.html) and [18-category common settings](https://sakura-editor.github.io/help/HLP000076.html) demonstrate menu/toolbar/editor/status composition, dense property pages, trees, and dialogs.
- [FFFTP's Japanese resource definition](https://github.com/ffftp/ffftp/blob/master/Resource/ffftp.ja-JP.rc) provides primary evidence for compact dialog units, controls, menus, and command rows.
- [Lhaplus author site](https://www7a.biglobe.ne.jp/~schezo/) and [Vector's 2000 review](https://www.vector.co.jp/magazine/softnews/001209/n0012091.html) show utility-centered simple/detailed settings and progress/dialog workflows.

The theme therefore models an information architecture, not a Japanese color palette or Y2K fashion style.

## Licensing and assets

- Microsoft's [font redistribution FAQ](https://learn.microsoft.com/en-us/typography/fonts/font-faq) and [copyright permissions](https://www.microsoft.com/en-us/legal/intellectualproperty/copyright/permissions) informed the no-extracted-assets rule.
- [98.css](https://github.com/jdan/98.css), [XP.css](https://github.com/botoxparty/XP.css), and [7.css](https://github.com/khang-nd/7.css) are MIT CSS frameworks and useful interoperability references. They are not vendored. Font/image sub-assets can have separate terms and must be audited independently.

All bundled control rendering is original CSS using borders, gradients, shadows, and installed system-font fallbacks.
