import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';
export default defineConfig({
  resolve: { alias: { '~': fileURLToPath(new URL('../../vendor/swisstaxcalculator', import.meta.url)) } },
  test: { include: ['scripts/tax/**/*.test.ts'], testTimeout: 120000 },
});
