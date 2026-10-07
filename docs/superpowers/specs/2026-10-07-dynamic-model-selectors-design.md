# Dynamic OpenRouter Model Selectors

## Goal

Allow users to select different OpenRouter models for each planning-council role using a dynamically loaded, searchable model catalog.

## Frontend behavior

Add four independent role selectors:

- Optimal Agent
- Satisficing Agent
- Agile Agent
- Judge/Chairman

The model names must not be hard-coded in the frontend. The frontend loads them from `GET /api/models`, stores the catalog in component state, and filters it locally as the user searches by model ID, display name, or provider.

The interface must show loading and error states and preserve one selected model ID per role. The selected values are sent with the existing solve request under `user_constraints.models`.

## Backend model catalog

Add `GET /api/models` to the FastAPI application. The backend fetches OpenRouter's public catalog from `https://openrouter.ai/api/v1/models`, normalizes the response, and caches it in memory for five minutes.

- Return the cached catalog while the cache is fresh.
- If refresh fails and stale data exists, return the stale catalog and log the refresh failure.
- If no catalog exists, return an explicit server error.
- Do not expose the OpenRouter API key to the browser.

## Backend role overrides

Extend the solve request handling to accept optional role model IDs under `user_constraints.models`:

```json
{
  "models": {
    "optimal": "provider/model-id",
    "satisficing": "provider/model-id",
    "agile": "provider/model-id",
    "judge": "provider/model-id"
  }
}
```

Use separate role selectors with backend override support. Validate every provided model ID against the current catalog and return HTTP 400 for unknown or blank values. When overrides are omitted, retain the environment-configured defaults from `backend/config.py`.

Pass the resolved role models through `run_full_council` and the three council stages without changing prompts, planner execution, fallback planning, telemetry, or offline council fallback behavior.

## Data flow

```text
OpenRouter model catalog
        |
        v
GET /api/models
        |
        v
Frontend searchable role selectors
        |
        v
POST /api/solve-pddl
        |
        v
Validated role overrides
        |
        v
Stage 1 -> Stage 2 -> Judge
```

## Error handling and compatibility

Catalog failures must be explicit. Stale cached data may be used only when a prior successful catalog exists. Existing solve requests without model overrides remain valid and use configured defaults. Existing planner and council fallback behavior remains unchanged.

## Validation

- Test the model catalog endpoint and cache/failure behavior.
- Test valid role overrides reach the appropriate council calls.
- Test unknown and blank model IDs return HTTP 400.
- Test requests without overrides retain defaults.
- Run backend tests, frontend lint/build, and `git diff --check`.
