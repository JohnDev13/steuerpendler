import { defineConfig } from 'vitest/config';
export default defineConfig({ test: { include: ['src/**/*.test.ts', 'scripts/**/*.test.ts'], exclude: ['vendor/**','node_modules/**'], maxWorkers: 2 } });
