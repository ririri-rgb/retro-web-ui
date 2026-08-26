# Framework and styling integration

## Static HTML and vanilla JavaScript

Add the generated CSS, place `data-retro-theme` on the application root, and adapt semantic HTML directly. Preserve IDs, form attributes, listener targets, and DOM query assumptions. Re-run listener-driven flows after moving nodes.

## React and React meta-frameworks

Keep component props, handler references, keys, controlled values, hooks, server actions, and server/client boundaries. Add theme CSS through the project's existing global-style entry. Avoid converting controlled library widgets to local-state replicas. In Next.js, preserve routing components, forms/actions, hydration boundaries, and metadata.

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

## CSS-in-JS and component libraries

Prefer provider/theme tokens for safe primitives and scoped wrappers for composition. Shadow DOM, closed components, canvas-rendered UI, cross-origin iframes, proprietary generated markup, and heavily virtualized widgets are best-effort. Do not use `!important` floods to simulate success.

When dependency CSS survives, inspect computed styles rather than assuming a later bundle resets them. Targeted adapters may need to neutralize explicit `height`, `min-height`, padding, positioning, transforms, shadows, pseudo-elements, and responsive rules on the original component selector. Keep the adapter under the theme root, use the narrowest selector that wins by source order/specificity, and rerun every affected interaction; do not solve one collision with a global reset.

## Generic fallback

When stack detection is uncertain, use a scoped CSS bundle plus targeted semantic markup edits. Never inject a global reset into an unknown application. Document components that cannot be themed without unsafe behavior changes.
