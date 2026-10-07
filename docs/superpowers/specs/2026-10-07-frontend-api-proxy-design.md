# Frontend API Proxy

## Goal

Route frontend API calls through the Vite development server so the browser uses same-origin `/api` requests instead of directly calling the backend on port 8001.

## Design

Configure a Vite proxy in `frontend/vite.config.js`:

- Match `/api`.
- Forward requests to `http://localhost:8001`.
- Preserve the request path and support the existing HTTP methods.

Update `frontend/src/api.js` to use `/api` as its base path. All current endpoint paths remain unchanged, including PDDL status, solving, telemetry, and legacy conversation routes.

The FastAPI CORS configuration remains in place for direct API consumers and alternate development clients; this change removes the browser's dependency on CORS for the standard Vite development flow.

## Validation

- Run `npm run lint`.
- Run `npm run build`.
- Confirm the built frontend has no hard-coded `http://localhost:8001` API calls.
- Inspect the final diff for unrelated changes.
