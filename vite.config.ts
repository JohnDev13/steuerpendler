import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';
const release=JSON.parse(readFileSync(new URL('./site/data/release.json',import.meta.url),'utf8'));
export default defineConfig({ publicDir: 'site', define:{__DATA_RELEASE__:JSON.stringify(release)}, server: { host: '127.0.0.1' }, build: { target: 'es2022' } });
