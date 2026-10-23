import { defineConfig } from '@playwright/test';
const base=process.env.PAGES_BASE||'/',port=process.env.PORT||'4173';
export default defineConfig({testDir:'./tests/e2e',fullyParallel:false,workers:1,
 use:{baseURL:`http://127.0.0.1:${port}${base}`,browserName:'chromium',trace:'retain-on-failure'},
 webServer:{command:'npm run build && node scripts/preview-server.mjs',url:`http://127.0.0.1:${port}${base}`,reuseExistingServer:false,timeout:60000},reporter:'list'});
