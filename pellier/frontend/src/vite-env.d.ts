/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_AWS_REGION: string;
  readonly VITE_ENABLE_AGENTS?: string;
  readonly VITE_ENABLE_CHAT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}