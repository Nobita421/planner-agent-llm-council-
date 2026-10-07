# Searchable Role Dropdowns

## Goal

Make council model selection user-friendly by replacing the shared search field and native selects with four independent searchable dropdowns.

## Interaction

Each role has its own model picker:

- Optimal Agent
- Satisficing Agent
- Agile Agent
- Judge / Chairman

The picker shows the current model in a clear card. Clicking it opens a dropdown containing a role-specific search field and filtered model cards. Each card displays the model name, provider, full ID, and pricing availability when present. Selecting a card immediately assigns the model and closes the dropdown.

Only one dropdown is open at a time. Searching one role does not affect the other roles. The existing reset-to-defaults action remains available.

## Compatibility

Continue loading models from `GET /api/models` and submitting role IDs through `user_constraints.models`. No backend changes are required. Preserve loading, catalog error, disabled, responsive, and empty-result states.

## Accessibility

Use labelled buttons/inputs, keyboard-focusable controls, and clear expanded/open state. Keep selected model text visible without requiring the dropdown to be open.

## Validation

- Verify each role opens its own dropdown.
- Verify each dropdown has independent search state.
- Verify selecting a card updates only its role and closes the dropdown.
- Verify model name, provider, and ID are visible.
- Verify reset-to-defaults still works.
- Run frontend build and browser smoke tests.
