# Acne Advisor AI Frontend

React/Vite client for the Acne Advisor AI chat UI.

## Local Commands

```powershell
npm ci
npm run build
npm run lint
```

The API base URL is read from `VITE_API_URL`. If it is unset, the frontend
client falls back to `http://127.0.0.1:8000`.

Do not commit `node_modules/` or `dist/`; both are generated local artifacts.
