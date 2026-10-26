import { defineConfig } from 'vitest/config'

// Component tests run in jsdom; JSX is compiled by esbuild (no Vite plugin needed).
export default defineConfig({
  esbuild: { jsx: 'automatic' },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.tsx'],
  },
})
