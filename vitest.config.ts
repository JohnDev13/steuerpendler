import {defineConfig} from 'vitest/config';
import {fileURLToPath} from 'node:url';
export default defineConfig({resolve:{alias:{'~':fileURLToPath(new URL('./vendor/swisstaxcalculator',import.meta.url))}},test:{include:['src/**/*.test.ts','scripts/**/*.test.ts'],exclude:['vendor/**','node_modules/**'],maxWorkers:2,testTimeout:120000}});
