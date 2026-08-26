# Behavior preservation contract

## Protected surface

Assume these are behavior, even when embedded in a UI component: network requests and headers; authentication and authorization; route targets and guards; state transitions; handler bodies; form names, actions, methods, values, and validation; storage keys and schemas; timers and subscriptions; database/backend code; analytics and audit events; accessibility state; and test selectors used by automation.

## Safe default changes

- CSS, theme tokens, visual wrappers, class names added alongside existing ones, and layout containers.
- Markup reordering only after checking focus order, DOM-dependent selectors, form ownership, event propagation, hydration, and tests.
- Semantic control replacement only when value, disabled/read-only state, callbacks, keyboard behavior, and accessible naming remain equivalent.

## High-risk changes

- Moving an input outside its form, replacing a submit button with a generic element, or changing `name`, `value`, `type`, `action`, or `method`.
- Recreating a controlled component with local state, changing event type/order, removing `preventDefault`, or changing bubbling.
- Replacing router links with anchors or buttons, altering URL construction, or changing server/client component boundaries.
- Styling by changing API response shapes, business predicates, storage keys, or backend contracts.
- Global resets that leak outside the themed root, remove focus outlines, or hide native controls without an accessible replacement.

## Review protocol

1. Inventory important user flows and protected signals before editing.
2. Prefer additive visual edits. If structural work is necessary, state the invariant that must survive.
3. Keep the original event expression or handler reference verbatim where practical.
4. Compare the hashed guard output and inspect every changed file manually.
5. Verify observable behavior. Passing builds alone are insufficient.

`behavior_guard.py` records hashes and counts, never source excerpts. It can detect removed or moved signals but cannot prove runtime equivalence, distinguish every alias, or understand dynamic code.
