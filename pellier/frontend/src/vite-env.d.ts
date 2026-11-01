/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Preferred. Same-origin `/api` when unset (Vite proxy / Workshop path). */
  readonly VITE_API_URL?: string;
  /** Legacy alias — read by code when VITE_API_URL is unset. */
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_AWS_REGION: string;
  readonly VITE_ENABLE_AGENTS?: string;
  readonly VITE_ENABLE_CHAT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}