import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';

// Deliberately serves the source drafts, not Vite output: build/Pages wiring belongs to integration.
const names = ['impressum', 'datenschutz', 'methode'];
const files = new Map(names.map(name => [`/pages/${name}.html`, readFileSync(new URL(`../../pages/${name}.html`, import.meta.url))]));

test('German static drafts: real HTTP, responsive light/dark, keyboard access, one document request and no cookies', async t => {
  const server = createServer((req, res) => {
    const file = files.get(req.url?.split('#')[0]);
    res.writeHead(file ? 200 : 404, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(file || 'Not found');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  t.after(() => browser.close());
  t.diagnostic(`Chromium ${browser.version()}; source-only HTTP verification, not production/Pages acceptance`);

  for (const name of names) {
    for (const [colorScheme, width] of [['light', 400], ['dark', 320]]) {
      await t.test(`${name} ${colorScheme} ${width}px`, async () => {
        const context = await browser.newContext({ viewport: { width, height: 800 }, colorScheme });
        try {
          const page = await context.newPage();
          const requests = [], errors = [];
          page.on('pageerror', error => errors.push(error.message));
          page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
          await context.route('**/*', route => {
            requests.push(route.request().url());
            return route.request().url().startsWith(origin) ? route.continue() : route.abort();
          });
          const url = `${origin}/pages/${name}.html`;
          const response = await page.goto(url, { waitUntil: 'networkidle' });
          assert.equal(response.status(), 200);
          assert.equal(await page.locator('html').getAttribute('lang'), 'de-CH');
          assert.equal(await page.locator('h1').count(), 1);
          assert.equal(await page.locator('script, iframe, img, object, embed, link, video, audio').count(), 0);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no horizontal overflow');
          await page.keyboard.press('Tab');
          assert.equal(await page.locator('.skip').evaluate(node => node === document.activeElement), true);
          await page.keyboard.press('Enter');
          assert.equal(new URL(page.url()).hash, '#inhalt');
          if (name === 'methode') {
            await page.locator('summary').focus();
            await page.keyboard.press('Enter');
            assert.equal(await page.locator('details').getAttribute('open'), '');
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'licence notice wraps');
          }
          assert.deepEqual(await context.cookies(), []);
          assert.deepEqual(requests, [url], 'no embedded resources or external requests');
          assert.deepEqual(errors, []);
          t.diagnostic(`${name} ${colorScheme}: HTTP 200, ${width}px, 1 HTML request, 0 cookies, 0 page/console errors`);
        } finally {
          await context.close();
        }
      });
    }
  }
});
