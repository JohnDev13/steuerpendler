import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
test('source CI keeps preview checks and the real failing tax-accuracy gate separate and fail-closed',()=>{
 const workflow=readFileSync('.github/workflows/ci.yml','utf8');
 for(const command of ['npm ci','npm test','npm run map:test','npm run release:test','npm run test:e2e','npm run tax:test','unittest discover','tests/content/','npx playwright install --with-deps chromium'])assert.ok(workflow.includes(command),command);
 assert.match(workflow,/contents: read/);assert.match(workflow,/persist-credentials: false/);
 assert.match(workflow,/preview:/);assert.match(workflow,/tax-accuracy:/);
 assert.doesNotMatch(workflow,/continue-on-error|passWithNoTests|\|\| true/);
 for(const line of workflow.split('\n').filter(line=>line.includes('uses:')))assert.match(line,/@[a-f0-9]{40}/);
});
