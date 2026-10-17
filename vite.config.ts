import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const release=JSON.parse(readFileSync(new URL('./site/data/release.json',import.meta.url),'utf8'));
export default defineConfig({
 base:process.env.PAGES_BASE||'/',publicDir:'site',define:{__DATA_RELEASE__:JSON.stringify(release)},
 server:{host:'127.0.0.1'},
 build:{target:'es2022',rollupOptions:{input:Object.fromEntries(['index.html','pages/impressum.html','pages/datenschutz.html','pages/methode.html'].map(path=>[path,fileURLToPath(new URL(path,import.meta.url))]))}}
});
