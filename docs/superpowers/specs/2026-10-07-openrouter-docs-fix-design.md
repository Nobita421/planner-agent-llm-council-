# OpenRouter Authentication and API Documentation Fix

## Goal

Correct the OpenRouter authentication header and bring the README API response example in line with the current FastAPI implementation.

## Scope

### OpenRouter client

Update `backend/openrouter.py` to use the configured `OPENROUTER_API_KEY` as a Bearer token. When the key is absent, avoid sending an invalid authorization header so the existing offline/mock fallback behavior remains usable. Do not log credentials or change response parsing, timeout behavior, or parallel request orchestration.

### README API documentation

Update the `POST /api/solve-pddl` response example in `README.md` to use the actual top-level `debate` field and current nested response shape, including:

- `stage1`
- `stage2`
- `aggregate_rankings`
- `judge_verdict`
- `execution`
- `validation`
- `xai_summary`
- `telemetry_id`

Clarify that `OPENROUTER_API_KEY` enables live OpenRouter requests and that omitting it preserves offline/mock council behavior.

## Data flow

```text
OPENROUTER_API_KEY
        |
        v
backend/config.py
        |
        v
backend/openrouter.py
        |
        +--> Bearer Authorization header when configured
        +--> no invalid auth header when absent
        |
        v
backend/council.py
        |
        v
backend/main.py /api/solve-pddl
```

## Error handling

The existing request failure handling remains unchanged: model request failures are logged without exposing secrets and the council continues using its existing fallback behavior. No broad exception handling or success-shaped response changes are introduced.

## Validation

Run the focused backend council and pipeline tests, then verify the final diff is limited to the OpenRouter client, README documentation, and this specification.
