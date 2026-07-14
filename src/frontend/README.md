# Acne Advisor AI Frontend

React/Vite client for the Acne Advisor AI chat UI.

## Local Commands

```powershell
npm ci
npm run build
npm run lint
```

The API base URL is read from `VITE_API_URL`. If it is unset, the frontend
client falls back to `http://127.0.0.1:8000`. The same resolved base URL is used
for `/health`, `/models`, `/chat`, and chat-history endpoints.

During local development the sidebar distinguishes backend states:

- `checking` / `recovering`: frontend is retrying health checks.
- `connected`: backend and required dependencies are ready.
- `degraded`: backend is reachable, but one dependency is not ready.
- `disconnected`: health timed out or the backend is not reachable.

HTTP responses from `/chat` such as 400, 429, 503, and 504 are treated as
backend-reachable provider/API errors, not as network disconnection.

Do not commit `node_modules/` or `dist/`; both are generated local artifacts.
