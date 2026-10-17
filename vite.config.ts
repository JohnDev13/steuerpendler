import { defineConfig } from 'vite';
export default defineConfig({ publicDir: 'site', server: { host: '127.0.0.1' }, build: { target: 'es2022' } });
