import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { createServer } from 'vite';

const root = fileURLToPath(new URL('../..', import.meta.url));
const destinations = [
  [261, 'Zürich', 'ZH'], [351, 'Bern', 'BE'], [1061, 'Luzern', 'LU'],
  [1201, 'Altdorf (UR)', 'UR'], [1372, 'Schwyz', 'SZ'], [1407, 'Sarnen', 'OW'],
  [1509, 'Stans', 'NW'], [1632, 'Glarus', 'GL'], [1711, 'Zug', 'ZG'],
  [2601, 'Solothurn', 'SO'], [2701, 'Basel', 'BS'], [2829, 'Liestal', 'BL'],
  [2939, 'Schaffhausen', 'SH'], [3001, 'Herisau', 'AR'], [3101, 'Appenzell', 'AI'],
  [3203, 'St. Gallen', 'SG'], [3901, 'Chur', 'GR'], [4001, 'Aarau', 'AG'],
  [4566, 'Frauenfeld', 'TG'],
];

// Synthetic browser fixtures only: these are not Swiss tax or timetable references.
const gemeinden = Object.fromEntries(destinations.map(([id, name, canton]) => [id, [name, canton, 100, 100, 0, 0]]));
const access = Object.fromEntries(destinations.map(([id, name]) => [id, [`synthetic-${id}`, `${name} Testhalt`, 11]]));
const profile = {
  meta: { year: 2026, incomes: { from: 40000, step: 1000, count: 461 } },
  cantons: { synthetic: Array.from({ length: 461 }, () => [0, 0, 0]) },
};
const release = {
  schemaVersion: 1,
  release: 'synthetic-browser-fixture',
  taxYear: 2026,
  availability: { tax: true, map: false, travel: true },
  approvals: { estv: false },
  status: 'fixture',
};

function fixtureFor(pathname) {
  if (pathname.endsWith('/data/gemeinden-2026.json')) return { gemeinden };
  if (pathname.endsWith('/data/tax-2026-s-0.json')) return profile;
  if (pathname.endsWith('/data/travel/access.json')) return { gemeinden: access };
  if (pathname.endsWith('/data/travel/meta.json')) return { fixture: true };
  if (pathname.endsWith('/data/travel/to/261.json')) return { to: 261, rows: [[261, 0], [351, 10]] };
  return null;
}

test('browser distinguishes no reachable Gemeinde from reachable Gemeinden with all tax data withheld', async t => {
  const vite = await createServer({
    configFile: false,
    root,
    publicDir: false,
    define: { __DATA_RELEASE__: JSON.stringify(release) },
    server: { host: '127.0.0.1', port: 0 },
  });
  await vite.listen();
  t.after(() => vite.close());
  const address = vite.httpServer.address();
  assert(address && typeof address === 'object');

  const browser = await chromium.launch({ headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage();
  await page.route('**/data/**', route => {
    const fixture = fixtureFor(new URL(route.request().url()).pathname);
    return fixture === null
      ? route.fulfill({ status: 404, contentType: 'text/plain', body: 'Missing synthetic fixture' })
      : route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) });
  });

  await page.goto(`http://127.0.0.1:${address.port}/`);
  await assert.doesNotReject(() => page.locator('#empty-state').waitFor({ state: 'visible' }));
  assert.equal(await page.locator('#summary').textContent(), '0 vergleichbare Gemeinden in Reichweite');
  assert.equal(await page.locator('#review-summary').textContent(), '');

  await page.locator('#max-walk').evaluate(element => {
    element.value = '15';
    element.dispatchEvent(new Event('input', { bubbles: true }));
  });

  await page.locator('#review-summary').waitFor({ state: 'visible' });
  assert.equal(await page.locator('#review-summary').textContent(), 'Für alle 2 erreichbaren Gemeinden werden die Daten geprüft.');
  assert.equal(await page.locator('#empty-state').isHidden(), true);
  assert.equal(await page.locator('#summary').textContent(), '0 vergleichbare Gemeinden in Reichweite');
  assert.equal(await page.locator('#ranked-list tr').count(), 0);
  assert.equal(await page.locator('#cheapest').textContent(), '');
});
