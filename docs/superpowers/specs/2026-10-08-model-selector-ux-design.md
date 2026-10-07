# Model Selector UX Improvements

## Goal

Make the dynamic council model selector easier to understand and use without changing its backend contract or model-selection behavior.

## Layout

Move the Council Models panel outside the Domain PDDL editor column so it appears as a full-width configuration section below the two PDDL editors. Keep the existing four independent role selectors:

- Optimal Agent
- Satisficing Agent
- Agile Agent
- Judge / Chairman

## Usability

Add:

- A live count of models matching the current search query.
- A reset-to-defaults action that restores the backend-provided default model for every role.
- A visible selected model ID beneath each role selector so long model names remain identifiable.

Preserve:

- Dynamic loading from `GET /api/models`.
- Local search by model name, provider, and ID.
- Loading and error states.
- Independent role selection state.
- Submission through `user_constraints.models`.

## Validation

- Verify the model panel is full-width and no longer nested inside the domain editor.
- Verify search count updates with the query.
- Verify reset restores all four backend defaults.
- Verify changing one selector does not change the other three.
- Run the frontend build and inspect the final diff.
