import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';


export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('.', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
  },
  test: {
    environment: 'node',
    include: ['**/*.test.{ts,tsx}'],
  },
});
