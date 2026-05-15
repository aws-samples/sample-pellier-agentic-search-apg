/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/** Strip trailing slash; empty string means root (no path prefix). */
function normalizeBasePath(raw: string | undefined): string {
  const b = (raw || '/').replace(/\/$/, '')
  return b === '/' ? '' : b
}

const workshopBase = normalizeBasePath(process.env.VITE_BASE_PATH)
const transcribeWsProxyPrefix = workshopBase ? `${workshopBase}/ws` : '/ws'

// Configuration for AWS Workshop Studio with CloudFront + VSCode Server
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    css: false,
    // The `.mjs` scanner in src/__tests__/copy.test.mjs is a standalone
    // Node script, not a vitest suite. It's invoked directly via
    // `node src/__tests__/copy.test.mjs` (see package.json / CI).
    //
    // e2e/ holds Playwright specs (different runner, different imports).
    exclude: ['**/node_modules/**', '**/dist/**', '**/*.test.mjs', 'e2e/**'],
  },
  // Base path strategy:
  //   - local prod build served by FastAPI on port 8000 → root-relative "/".
  //   - Workshop Studio / CloudFront deployments set VITE_BASE_PATH
  //     explicitly via the CFN so the built bundle matches whatever
  //     prefix CloudFront forwards to the origin (e.g. "/ports/8000/").
  // Keeping this flag-driven (instead of a hardcoded "/ports/5173/")
  // means dev + local prod + Workshop Studio all read from the same
  // vite config without a conditional NODE_ENV branch.
  base: process.env.VITE_BASE_PATH || '/',
  
  plugins: [react()],
  
  server: {
    host: true,  // Allow all hosts (required for CloudFront)
    port: 5173,
    strictPort: true,

    // Allow Vite to serve files from outside the project root so a
    // worktree (under .claude/worktrees/) that symlinks node_modules
    // back to the main repo can still resolve dependency files. The
    // default `fs.allow` only includes the project root + Vite's own
    // client; without this, woff2 / .css from @fontsource* etc. 403.
    fs: {
      allow: ['..', '../..', '../../..', '../../../..'],
    },

    // API + Transcribe WebSocket proxy (Workshop Studio: browser cannot open :8000)
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      [transcribeWsProxyPrefix]: {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => '/ws' + path.slice(transcribeWsProxyPrefix.length),
      },
    },
  },
  
  build: {
    outDir: 'dist',
    sourcemap: true,
    // Cache busting: Add hash to filenames for workshop reliability
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].[hash].js',
        chunkFileNames: 'assets/[name].[hash].js',
        assetFileNames: 'assets/[name].[hash].[ext]'
      }
    }
  },
})
