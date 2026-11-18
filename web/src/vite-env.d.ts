/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  // "demo" (default): accounts and saved-trip lists in this browser. "server": the backend's
  // /auth and /me/trips endpoints (see web/BACKEND-HANDOFF.md).
  readonly VITE_AUTH_MODE?: "demo" | "server";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
