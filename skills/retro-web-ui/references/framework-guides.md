# Framework and styling integration

## Static HTML and vanilla JavaScript

Add the generated CSS, place `data-retro-theme` on the application root, and adapt semantic HTML directly. Preserve IDs, form attributes, listener targets, and DOM query assumptions. Re-run listener-driven flows after moving nodes.

## React and React meta-frameworks

Keep component props, handler references, keys, controlled values, hooks, server actions, and server/client boundaries. Add theme CSS through the project's existing global-style entry. Avoid converting controlled library widgets to local-state replicas. In Next.js, preserve routing components, forms/actions, hydration boundaries, and metadata.

For request-rendered applications, put the theme attribute in stable server HTML when the entire application is converted. Do not add it only after hydration: that creates a flash and can produce a server/client attribute mismatch. Keep interactive conversion code in the existing client island rather than pulling an otherwise server-rendered layout into the client bundle.

## Vue and Nuxt

Preserve `v-model`, `:key`, event modifiers, slots, transitions that communicate state, and SSR-safe composition. If scoped CSS blocks theme rules, import the bundle globally or use a deliberate `:deep()` bridge limited to the themed root.

## Svelte and SvelteKit

Preserve bindings, actions, event modifiers, keyed blocks, form actions, stores, and load boundaries. Put shared theme CSS in the established global entry rather than fighting component scoping.

## Angular

Preserve reactive/template form bindings, router directives, outputs, DI, change-detection assumptions, and Material accessibility behavior. Global theme CSS may need a dedicated layer; structural replacement is higher risk and remains best-effort unless existing tests cover it.

## Tailwind and utility CSS

Do not mechanically replace every class. Add a scoped retro component layer and remove conflicting utilities from touched structures. Retain state variants and responsive/visibility utilities that encode behavior. Arbitrary values and generated class names require manual review.

## Bootstrap

Load scoped retro overrides after Bootstrap or map markup to the bundled retro classes. Preserve collapse, dropdown, modal, validation, and data attributes. Test JavaScript plugins because wrapper changes can break selector assumptions.

Wait for the plugin's lifecycle event (`shown.bs.modal`, `hidden.bs.modal`, and equivalents) instead of an arbitrary delay. Bootstrap utilities with `!important` can survive a later theme bundle. If a touched element still has a modern pill radius, shadow, or color, override the exact utility/component combination under the theme root; a narrowly scoped `!important` is acceptable when it is required to beat an upstream utility that also uses `!important`.

## CSS-in-JS and component libraries

Prefer provider/theme tokens for safe primitives and scoped wrappers for composition. Shadow DOM, closed components, canvas-rendered UI, cross-origin iframes, proprietary generated markup, and heavily virtualized widgets are best-effort. Do not use `!important` floods to simulate success.

When dependency CSS survives, inspect computed styles rather than assuming a later bundle resets them. Targeted adapters may need to neutralize explicit `height`, `min-height`, padding, positioning, transforms, shadows, pseudo-elements, and responsive rules on the original component selector. Keep the adapter under the theme root, use the narrowest selector that wins by source order/specificity, and rerun every affected interaction; do not solve one collision with a global reset.

Prefer the component library's current slot/component-override API. Version-specific deprecated passthrough props can attach test, ARIA, or native input attributes to the wrong wrapper without a type or build failure. Verify the final DOM node, accessible name, controlled value, portal surface, Escape behavior, and focus return in a real browser.

## Theme roots and portals

For a whole-application conversion, a stable theme root on `body` or the app shell is appropriate and naturally contains body-hosted dialogs, menus, and popovers. For a partial route or surface conversion, keep the permanent theme root local to that surface. If a library portals overlays to `body`, either configure a portal container inside the local root or mirror the theme attribute onto the portal host only while the converted surface is mounted. Remove the mirrored attribute on route/component teardown and verify the next unconverted route is not themed.

Never leave a global body theme in place merely to style one converted login, settings, or modal surface. That can silently restyle unrelated routes even when the converted screen itself looks correct.

## Generic fallback

When stack detection is uncertain, use a scoped CSS bundle plus targeted semantic markup edits. Never inject a global reset into an unknown application. Document components that cannot be themed without unsafe behavior changes.
