import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: process.env.NEXT_DIST_DIR || '.next',
  // Playwright uses an isolated distDir and `next start`; standalone output
  // is retained for the default production build used by the container.
  output: process.env.NEXT_DIST_DIR ? undefined : 'standalone',
  outputFileTracingRoot: frontendRoot,
  turbopack: {
    root: frontendRoot,
  },
};

export default nextConfig;
